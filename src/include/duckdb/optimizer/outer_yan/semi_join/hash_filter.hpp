//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/hash_filter.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/limits.hpp"
#include "duckdb/common/types.hpp"
#include "duckdb/common/types/data_chunk.hpp"
#include "duckdb/common/types/selection_vector.hpp"
#include "duckdb/common/types/value.hpp"
#include "duckdb/common/vector.hpp"

namespace duckdb {

// =============================================================================
// HashFilter — exact set-membership fallback when KeyBitmap doesn't apply
// =============================================================================
//
// Used as the HASH branch of SemiJoinFilter when:
//   - The build key type is not bitmap-eligible (varchar, decimal, etc.)
//   - The key range exceeds PRAGMA outer_yan_bitmap_max_bytes * 8
//   - Composite build keys (v1: bitmap only supports single-column)
//
// Design — open-addressed hash set with linear probing, MurmurHash64A on
// the concatenation of per-column Value::Hash() outputs. Inspired by Apache
// Arrow Acero's `SwissTable`/`KeyEncoder` and DuckDB's `JoinHashTable` but
// pared down to exact set-membership (no rowstore, no projection, no probe
// scan structure). Slot layout:
//
//     Slot { hash_t full_hash; idx_t key_index_or_EMPTY; }
//
// `slots_` is a power-of-2 array (probed via `hash & mask_`). Stored keys
// live in `stored_keys_` (one vector<Value> per unique build tuple).
// Collisions follow linear probing — `(idx + 1) & mask_` — chosen for
// cache friendliness over double hashing.
//
// Concurrency model: each thread builds a thread-local HashFilter, all of
// which are folded into the global one at Combine/Finalize via Merge. So
// neither Build nor Contains needs internal synchronisation. Merge is
// single-threaded by construction (called once at Finalize).
//
// Exact semantics: no false positives. NULL keys are skipped at Build time
// and at probe time (semi-join NULL never matches).
class HashFilter {
public:
	// Hash variant — set at construction, immutable afterwards. Build and
	// Contains both route through `HashKey(key, kind_)`, so they're
	// guaranteed to agree (no risk of build/probe mismatch).
	//   MURMUR_HASH2  — stack-buffered MurmurHash64A over per-column digests.
	//   DUCKDB_COMBINE — CombineHash (XOR), matches `VectorOperations::Hash`
	//                    + `::CombineHash`. Cheaper per call; XOR-only mix
	//                    so adversarially weaker on synthetic inputs but
	//                    fine for non-adversarial workloads.
	enum class HashKind : uint8_t { MURMUR_HASH2, DUCKDB_COMBINE };

	explicit HashFilter(HashKind kind = HashKind::DUCKDB_COMBINE);
	~HashFilter();

	HashKind kind() const {
		return kind_;
	}

	// Extract the build-side join keys from `chunk` and insert them. NULL
	// keys are skipped. Idempotent: the table is a set (duplicate inserts
	// are no-ops). On the first call, captures `build_col_ids.size()` as
	// the arity and asserts it on subsequent Builds + every Contains.
	void Build(const DataChunk &chunk, const vector<idx_t> &build_col_ids);

	// Marks the filter probe-ready. Currently just a flag; reserved for
	// future repack / shrink-to-fit optimisations.
	void Finalize();

	// Per-row existence test. Asserts `key.size() == KeyArity()` once the
	// filter has seen any Build (catches column-count mismatches early
	// rather than silently returning false negatives).
	bool Contains(const vector<Value> &key) const;

	idx_t Count() const {
		return count_;
	}
	idx_t Capacity() const {
		return mask_ + 1;
	}
	bool IsEmpty() const {
		return count_ == 0;
	}
	bool IsFinalized() const {
		return finalized_;
	}
	// Arity captured at first Build. Returns 0 before any Build has run.
	idx_t KeyArity() const {
		return key_arity_;
	}

	// Reference-quality MurmurHash64A (Austin Appleby). Public so callers
	// can hash custom byte sequences with the same family used internally.
	static hash_t MurmurHash64A(const void *data, idx_t len, uint64_t seed = 0);
	// Dispatch on `kind`. Single entry point used by Build / Contains so
	// the two paths can never disagree on which hash they're computing.
	static hash_t HashKey(const vector<Value> &key, HashKind kind);
	// Stack-buffered MurmurHash64A over concatenated per-column digests.
	// Typical arities (≤ 8 columns) avoid the heap fallback.
	static hash_t HashKeyMurmur(const vector<Value> &key);
	// CombineHash (XOR) over per-column Value::Hash() outputs. Equivalent
	// to running `VectorOperations::Hash` + `::CombineHash` over the same
	// columns, so build (scalar) and a future vectorized probe path
	// produce byte-equal hashes.
	static hash_t HashKeyDuckDB(const vector<Value> &key);

private:
	struct Slot {
		hash_t hash;
		idx_t key_index; // EMPTY_KEY_INDEX when slot is free
	};

	static constexpr idx_t EMPTY_KEY_INDEX = NumericLimits<idx_t>::Maximum();
	// Power-of-2 starting capacity. Small so that filters over tiny build
	// sides don't waste memory on slot allocation.
	static constexpr idx_t INITIAL_CAPACITY = 64;
	// Refuse to grow beyond 2^60 slots. With Slot ≈ 16 B that's 16 EiB of
	// slot memory — past anything realistic. The bound exists so the
	// load-factor check (subtraction form) can't be approached by overflow.
	static constexpr idx_t MAX_CAPACITY = idx_t(1) << 60;

	// Load factor 3/4. Implemented as `count + additional > capacity - capacity/4`
	// so no multiplication is performed (former `* 4` / `* 3` form could
	// overflow idx_t for capacities near 2^62).
	void EnsureCapacityFor(idx_t additional);
	void Resize(idx_t new_capacity);
	// Insert (or no-op on duplicate). Caller supplies the pre-computed
	// `hash` so Build doesn't re-hash on the fast path.
	void InsertHashedKey(vector<Value> key, hash_t hash);
	static bool KeysEqual(const vector<Value> &a, const vector<Value> &b);

	vector<Slot> slots_;
	idx_t mask_ = 0; // capacity - 1
	vector<vector<Value>> stored_keys_;
	idx_t count_ = 0;
	bool finalized_ = false;
	// Set on the first Build call. Asserted on subsequent Builds and on
	// every Contains call — catches column-count mismatch bugs (e.g.
	// shared filter receiving probes from a different relation) early
	// rather than silently miscomputing.
	idx_t key_arity_ = 0;
	// Hash variant selected at construction; immutable.
	HashKind kind_ = HashKind::MURMUR_HASH2;
};

// =============================================================================
// HashFilterUseKernel — per-chunk probe kernel
// =============================================================================
//
// Per-row Contains check, walking `probe_col_ids` to extract each row's key
// tuple. SIMD acceleration is plausible (batched MurmurHash + gather) but
// deferred — KeyBitmap is the primary path in plan 3 and the HASH branch
// is rarely hot.
class HashFilterUseKernel {
public:
	//! Narrows `sel` in-place to surviving rows from `input`. `probe_col_ids`
	//! identify the join-key columns in `input`. NULL probe keys never match.
	static void filter(const DataChunk &input, const vector<idx_t> &probe_col_ids,
	                   const HashFilter &hash_filter, SelectionVector &sel, idx_t &approved);
};

} // namespace duckdb
