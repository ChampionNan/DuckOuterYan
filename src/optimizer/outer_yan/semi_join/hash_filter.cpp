#include "duckdb/optimizer/outer_yan/semi_join/hash_filter.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/common/types/hash.hpp"

#include <cstring>

namespace duckdb {

// =============================================================================
// MurmurHash64A (Austin Appleby, public domain)
// =============================================================================
//
// Reference: https://github.com/aappleby/smhasher (MurmurHash2 family). Same
// digest used by Apache Arrow Acero and various DuckDB internals for byte-
// sequence hashing. 64-bit output, designed for x86-64 (little-endian
// optimised) but works on big-endian via the byte-swap tail.
hash_t HashFilter::MurmurHash64A(const void *data, idx_t len, uint64_t seed) {
	constexpr uint64_t m = 0xc6a4a7935bd1e995ULL;
	constexpr int r = 47;

	uint64_t h = seed ^ (static_cast<uint64_t>(len) * m);

	auto data8 = reinterpret_cast<const uint8_t *>(data);
	while (len >= 8) {
		uint64_t k;
		std::memcpy(&k, data8, sizeof(k));
		k *= m;
		k ^= k >> r;
		k *= m;
		h ^= k;
		h *= m;
		data8 += 8;
		len -= 8;
	}

	switch (len) {
	case 7:
		h ^= static_cast<uint64_t>(data8[6]) << 48; // fall through
	case 6:
		h ^= static_cast<uint64_t>(data8[5]) << 40; // fall through
	case 5:
		h ^= static_cast<uint64_t>(data8[4]) << 32; // fall through
	case 4:
		h ^= static_cast<uint64_t>(data8[3]) << 24; // fall through
	case 3:
		h ^= static_cast<uint64_t>(data8[2]) << 16; // fall through
	case 2:
		h ^= static_cast<uint64_t>(data8[1]) << 8; // fall through
	case 1:
		h ^= static_cast<uint64_t>(data8[0]);
		h *= m;
	default:
		break;
	}

	h ^= h >> r;
	h *= m;
	h ^= h >> r;
	return h;
}

hash_t HashFilter::HashKey(const vector<Value> &key, HashKind kind) {
	// Single dispatch point. Build and Contains both come through here so
	// they cannot disagree on which variant they're hashing with.
	switch (kind) {
	case HashKind::MURMUR_HASH2:
		return HashKeyMurmur(key);
	case HashKind::DUCKDB_COMBINE:
		return HashKeyDuckDB(key);
	}
	throw InternalException("HashFilter::HashKey: unreachable HashKind");
}

hash_t HashFilter::HashKeyMurmur(const vector<Value> &key) {
	// Stack-buffered MurmurHash64A over concatenated per-column Value::Hash()
	// digests. INLINE_LIMIT = 8 covers ~all realistic semi-join keys
	// (typical 1-3 columns); the heap fallback is a safety valve for
	// unusual composites.
	constexpr idx_t INLINE_LIMIT = 8;
	if (key.size() <= INLINE_LIMIT) {
		hash_t inline_buf[INLINE_LIMIT];
		for (idx_t i = 0; i < key.size(); i++) {
			inline_buf[i] = key[i].Hash();
		}
		return MurmurHash64A(inline_buf, key.size() * sizeof(hash_t));
	}
	vector<hash_t> heap_buf;
	heap_buf.reserve(key.size());
	for (auto &v : key) {
		heap_buf.emplace_back(v.Hash());
	}
	return MurmurHash64A(heap_buf.data(), heap_buf.size() * sizeof(hash_t));
}

hash_t HashFilter::HashKeyDuckDB(const vector<Value> &key) {
	// Idiomatic DuckDB combine: CombineHash (XOR) over per-column
	// Value::Hash() outputs. Equivalent to `VectorOperations::Hash` +
	// `::CombineHash` so a future vectorized hot path would produce the
	// same `hash_t` per row. No allocation, single MOV + XOR per column.
	hash_t h = 0;
	for (auto &v : key) {
		h = CombineHash(h, v.Hash());
	}
	return h;
}

bool HashFilter::KeysEqual(const vector<Value> &a, const vector<Value> &b) {
	if (a.size() != b.size()) {
		return false;
	}
	for (idx_t i = 0; i < a.size(); i++) {
		if (!(a[i] == b[i])) {
			return false;
		}
	}
	return true;
}

HashFilter::HashFilter(HashKind kind) : kind_(kind) {
	// Pre-allocate the slot array so the hot path never sees an empty table.
	slots_.assign(INITIAL_CAPACITY, Slot {0, EMPTY_KEY_INDEX});
	mask_ = INITIAL_CAPACITY - 1;
}

HashFilter::~HashFilter() = default;

void HashFilter::EnsureCapacityFor(idx_t additional) {
	// Load factor 3/4. Subtraction form is overflow-safe: `count + additional`
	// stays bounded by realistic memory, and `capacity - capacity/4` doesn't
	// multiply. The former `* 4` / `* 3` formulation could overflow uint64_t
	// at capacities approaching 2^62 — unreachable in practice but defensive.
	while (count_ + additional > Capacity() - (Capacity() >> 2)) {
		if (Capacity() >= MAX_CAPACITY) {
			throw InternalException("HashFilter: capacity exceeds 2^60 slots");
		}
		Resize(Capacity() * 2);
	}
}

void HashFilter::Resize(idx_t new_capacity) {
	D_ASSERT((new_capacity & (new_capacity - 1)) == 0); // power of 2
	vector<Slot> new_slots;
	new_slots.assign(new_capacity, Slot {0, EMPTY_KEY_INDEX});
	idx_t new_mask = new_capacity - 1;

	// Rehash by reading existing slots' stored hashes (we kept them).
	for (auto &slot : slots_) {
		if (slot.key_index == EMPTY_KEY_INDEX) {
			continue;
		}
		idx_t idx = slot.hash & new_mask;
		while (new_slots[idx].key_index != EMPTY_KEY_INDEX) {
			idx = (idx + 1) & new_mask;
		}
		new_slots[idx] = slot;
	}
	slots_ = std::move(new_slots);
	mask_ = new_mask;
}

void HashFilter::InsertHashedKey(vector<Value> key, hash_t hash) {
	EnsureCapacityFor(1);
	idx_t idx = hash & mask_;
	while (true) {
		auto &slot = slots_[idx];
		if (slot.key_index == EMPTY_KEY_INDEX) {
			stored_keys_.emplace_back(std::move(key));
			slot.hash = hash;
			slot.key_index = stored_keys_.size() - 1;
			count_++;
			return;
		}
		// Same hash + same key tuple → already present (set semantics).
		if (slot.hash == hash && KeysEqual(stored_keys_[slot.key_index], key)) {
			return;
		}
		idx = (idx + 1) & mask_;
	}
}

void HashFilter::Build(const DataChunk &chunk, const vector<idx_t> &build_col_ids) {
	if (finalized_) {
		throw InternalException("HashFilter::Build called after Finalize");
	}
	if (build_col_ids.empty()) {
		throw InternalException("HashFilter::Build: empty build_col_ids");
	}

	// Capture arity on first call; assert consistency afterwards.
	if (key_arity_ == 0) {
		key_arity_ = build_col_ids.size();
	} else if (key_arity_ != build_col_ids.size()) {
		throw InternalException("HashFilter::Build: build_col_ids size changed across Builds (%llu vs %llu)",
		                        static_cast<unsigned long long>(key_arity_),
		                        static_cast<unsigned long long>(build_col_ids.size()));
	}

	const idx_t row_count = chunk.size();
	if (row_count == 0) {
		return;
	}

	// Resolve UnifiedVectorFormat per column ONCE. The previous
	// `chunk.GetValue(col, row)` loop did this resolution + a Value
	// allocation per cell, which dominates the build cost.
	vector<UnifiedVectorFormat> formats(build_col_ids.size());
	for (idx_t c = 0; c < build_col_ids.size(); c++) {
		chunk.data[build_col_ids[c]].ToUnifiedFormat(row_count, formats[c]);
	}

	vector<Value> key;
	key.reserve(build_col_ids.size());

	for (idx_t r = 0; r < row_count; r++) {
		// Null check via UnifiedVectorFormat — no Value allocation just to
		// observe NULL. Semi-join semantics: NULL keys never match, skip.
		bool any_null = false;
		for (idx_t c = 0; c < build_col_ids.size(); c++) {
			const auto &fmt = formats[c];
			const auto idx = fmt.sel->get_index(r);
			if (!fmt.validity.RowIsValid(idx)) {
				any_null = true;
				break;
			}
		}
		if (any_null) {
			continue;
		}

		// Materialize the key tuple only for rows that pass the null
		// check; Value is the storage format the set is keyed on.
		key.clear();
		for (auto col_id : build_col_ids) {
			key.emplace_back(chunk.GetValue(col_id, r));
		}
		InsertHashedKey(key, HashKey(key, kind_));
	}
}

void HashFilter::Finalize() {
	finalized_ = true;
}

bool HashFilter::Contains(const vector<Value> &key) const {
	// Arity guard — catches column-count mismatches before they silently
	// degrade into false negatives via differing HashKey / KeysEqual outputs.
	D_ASSERT(key_arity_ == 0 || key.size() == key_arity_);
	auto hash = HashKey(key, kind_);
	idx_t idx = hash & mask_;
	// Linear probe until we hit empty (definitive miss) or matching slot.
	while (true) {
		const auto &slot = slots_[idx];
		if (slot.key_index == EMPTY_KEY_INDEX) {
			return false;
		}
		if (slot.hash == hash && KeysEqual(stored_keys_[slot.key_index], key)) {
			return true;
		}
		idx = (idx + 1) & mask_;
	}
}

void HashFilterUseKernel::filter(const DataChunk &input, const vector<idx_t> &probe_col_ids,
                                 const HashFilter &hash_filter, SelectionVector &sel, idx_t &approved) {
	approved = 0;
	if (probe_col_ids.empty()) {
		throw InternalException("HashFilterUseKernel::filter: empty probe_col_ids");
	}
	if (hash_filter.IsEmpty()) {
		return;
	}
	// Catch column-count mismatch up front rather than per-row.
	if (hash_filter.KeyArity() != 0 && probe_col_ids.size() != hash_filter.KeyArity()) {
		throw InternalException("HashFilterUseKernel::filter: probe arity %llu does not match build arity %llu",
		                        static_cast<unsigned long long>(probe_col_ids.size()),
		                        static_cast<unsigned long long>(hash_filter.KeyArity()));
	}

	const idx_t row_count = input.size();
	if (row_count == 0) {
		return;
	}

	// Same UnifiedVectorFormat optimisation as Build — resolve once per
	// column, do per-row null check without Value allocation.
	vector<UnifiedVectorFormat> formats(probe_col_ids.size());
	for (idx_t c = 0; c < probe_col_ids.size(); c++) {
		input.data[probe_col_ids[c]].ToUnifiedFormat(row_count, formats[c]);
	}

	vector<Value> key;
	key.reserve(probe_col_ids.size());

	for (idx_t r = 0; r < row_count; r++) {
		bool any_null = false;
		for (idx_t c = 0; c < probe_col_ids.size(); c++) {
			const auto &fmt = formats[c];
			const auto idx = fmt.sel->get_index(r);
			if (!fmt.validity.RowIsValid(idx)) {
				any_null = true;
				break;
			}
		}
		// NULL probe keys never match (semi-join semantics).
		if (any_null) {
			continue;
		}

		key.clear();
		for (auto col_id : probe_col_ids) {
			key.emplace_back(input.GetValue(col_id, r));
		}
		if (hash_filter.Contains(key)) {
			sel.set_index(approved++, r);
		}
	}
}

} // namespace duckdb
