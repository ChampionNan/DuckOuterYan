//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/key_bitmap.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/allocator.hpp"
#include "duckdb/common/types.hpp"
#include "duckdb/common/types/data_chunk.hpp"
#include "duckdb/common/types/selection_vector.hpp"
#include "duckdb/common/unique_ptr.hpp"
#include "duckdb/common/vector.hpp"
#include "duckdb/main/client_context.hpp"

namespace duckdb {

class ColumnDataCollection;

// =============================================================================
// KeyBitmap — dense bit-per-value index over a build relation's join key.
// =============================================================================
//
// Used as the primary path of SemiJoinFilter when:
//   - Key column type is in {INTEGER, BIGINT, UINTEGER, UBIGINT, DATE}.
//   - For single-column keys, (max - min + 1) fits within the byte budget.
//   - For multi-column composite keys (v1: not supported — TryBuild returns
//     nullptr).
//
// Exact: a row r survives iff its key falls in [min,max] AND the corresponding
// bit is set. No false positives. Rows outside [min,max] are definitively not
// present in the build set.
class KeyBitmap {
public:
	KeyBitmap();

	// =========================================================================
	// Sequential build entry point.
	// =========================================================================
	//
	// Two-pass build over a materialised ColumnDataCollection. Returns nullptr
	// on any disqualifying condition; caller falls back to HashFilter.
	//
	// `build_col_ids` identify the join-key column(s) within rows of
	// `build_data`. `build_col_types` must align (same length, same order).
	// `byte_budget` is the per-filter cap from PRAGMA outer_yan_bitmap_max_bytes.
	//
	// Now a thin wrapper over the parallel-build helpers (CheckEligibility →
	// ScanMinMaxRange → Allocate → FillBitsRange<false> → FinalizePopCount).
	// The same primitives are driven from PhysicalSJBuild's SJBuildBitmap*Event
	// chain when running within-filter parallelism.
	static unique_ptr<KeyBitmap> TryBuild(ClientContext &context,
	                                      const ColumnDataCollection &build_data,
	                                      const vector<idx_t> &build_col_ids,
	                                      const vector<LogicalType> &build_col_types,
	                                      idx_t byte_budget);

	// =========================================================================
	// Parallel-build helpers (Stage 1).
	// =========================================================================
	//
	// These helpers split the sequential TryBuild into stages that can be
	// driven by SJBuildBitmapInitEvent (parallel min/max scan + allocation)
	// and SJBuildBitmapFillEvent (parallel bit-set + popcount), mirroring the
	// HashJoinTableInitEvent → HashJoinFinalizeEvent chain.

	//! Per-chunk-range reduction returned by ScanMinMaxRange. `non_null_rows`
	//! lets the reduce step distinguish "empty build" (emit empty bitmap)
	//! from "range too wide" (fall back to HashFilter).
	struct MinMaxRange {
		int64_t min_key;
		int64_t max_key;
		idx_t non_null_rows;
	};

	//! Eligibility verdict — single-column, bitmap-eligible physical type.
	//! Computed once in PhysicalSJBuild::Finalize before deciding whether to
	//! dispatch the parallel bitmap event chain or fall straight to hash.
	struct EligibilityResult {
		bool eligible;
		idx_t col_id;
		LogicalTypeId type_id;
	};
	static EligibilityResult CheckEligibility(const vector<idx_t> &build_col_ids,
	                                          const vector<LogicalType> &build_col_types);

	//! Per-task min/max scan of [chunk_from, chunk_to) of `build_data`. Thread-
	//! safe across calls: uses ColumnDataCollection::FetchChunk(idx), so each
	//! task owns its own DataChunk and never touches a shared scan cursor.
	static MinMaxRange ScanMinMaxRange(const ColumnDataCollection &build_data, idx_t col_id,
	                                   LogicalTypeId type_id, idx_t chunk_from, idx_t chunk_to);

	//! Single-threaded reduction over per-task MinMaxRange results. Called
	//! from SJBuildBitmapInitEvent::FinishEvent.
	static MinMaxRange ReduceMinMax(const vector<MinMaxRange> &locals);

	//! Allocate a KeyBitmap sized for `range`. Returns nullptr when the
	//! required bytes exceed `byte_budget` — caller falls back to HashFilter.
	//! When `range.non_null_rows == 0`, returns a special empty bitmap
	//! (min=0, max=-1, bit_count=0); the probe path filters everything against
	//! such a bitmap (IsEmpty short-circuits ProbeBatch).
	static unique_ptr<KeyBitmap> Allocate(ClientContext &context, const MinMaxRange &range,
	                                      const LogicalType &key_type, idx_t byte_budget);

	//! Per-task bit-set of [chunk_from, chunk_to) into this bitmap's word
	//! array. Thread-safe across concurrent calls when PARALLEL=true: per-bit
	//! writes use __atomic_or_fetch with memory_order_relaxed (we only need
	//! atomicity of the OR, not ordering between bits — the bit-set is a
	//! commutative monoid). PARALLEL=false uses plain `|=` for the sequential
	//! TryBuild fast path.
	template <bool PARALLEL>
	void FillBitsRange(const ColumnDataCollection &build_data, idx_t col_id, LogicalTypeId type_id,
	                   idx_t chunk_from, idx_t chunk_to);

	//! Compute popcount across all words. Single-threaded; called from
	//! SJBuildBitmapFillEvent::FinishEvent after all FillBitsRange tasks
	//! have finished. Stored in `pop_count_` and consumed by IsEmpty().
	void FinalizePopCount();

	// Scalar single-row probe. Used by tests; not on the hot path.
	bool Probe(int64_t flat_key) const;

	// Vectorised: narrows `sel` in-place to surviving rows from `input`, writes
	// the count to `approved`. Branchless gather + AND + in-range mask in the
	// hot loop. Scalar implementation here; SIMD specialisations belong in
	// key_bitmap_simd.cpp (per CLAUDE.md §2.3, scalar fallback is required).
	//
	// `probe_col_ids` identifies the probe-side join-key column(s) within
	// `input`. Must align with the bitmap's key shape (single-column for v1).
	void ProbeBatch(const DataChunk &input,
	                const vector<idx_t> &probe_col_ids,
	                SelectionVector &sel, idx_t &approved) const;

	int64_t MinKey() const { return min_key_; }
	int64_t MaxKey() const { return max_key_; }
	idx_t BitCount() const { return bit_count_; }
	idx_t SizeBytes() const { return bit_count_ / 8; }
	idx_t PopCount() const { return pop_count_; }
	bool IsEmpty() const { return pop_count_ == 0; }

private:
	// Owned bit array. Allocated through BufferManager's allocator so memory
	// is accounted against the buffer pool.
	AllocatedData buffer_;
	// 64-byte aligned pointer into `buffer_`. Loops over uint64_t words.
	uint64_t *words_ = nullptr;
	// Key range [min_key_, max_key_], inclusive on both ends.
	int64_t min_key_ = 0;
	int64_t max_key_ = 0;
	// Total bit capacity (always a multiple of 64).
	idx_t bit_count_ = 0;
	// Number of bits set (computed at end of Build, used by IsEmpty).
	idx_t pop_count_ = 0;
	// Original key type, retained for type-dispatch on probe.
	LogicalType key_type_ = LogicalType::INVALID;
};

} // namespace duckdb
