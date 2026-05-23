#include "duckdb/optimizer/outer_yan/semi_join/key_bitmap.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/common/limits.hpp"
#include "duckdb/common/numeric_utils.hpp"
#include "duckdb/common/types/column/column_data_collection.hpp"
#include "duckdb/common/types/date.hpp"
#include "duckdb/storage/buffer_manager.hpp"

#include <algorithm>
#include <cstring>

namespace duckdb {

KeyBitmap::KeyBitmap() = default;

namespace {

// Type-erased loader: read a key from `data + idx * sizeof(T)` as int64_t,
// for the physical type T that backs `type_id`. Supported types listed in
// IsBitmapEligibleType below.
template <typename T>
inline int64_t LoadAsInt64(const_data_ptr_t data, idx_t idx) {
	return static_cast<int64_t>(reinterpret_cast<const T *>(data)[idx]);
}

bool IsBitmapEligibleType(LogicalTypeId id) {
	switch (id) {
	case LogicalTypeId::INTEGER:
	case LogicalTypeId::BIGINT:
	case LogicalTypeId::UINTEGER:
	case LogicalTypeId::DATE:
		return true;
	default:
		// UBIGINT / UHUGEINT may overflow int64; defer.
		return false;
	}
}

// Per-row dispatch — small enough to inline at the switch site.
inline int64_t LoadKeyAsInt64(LogicalTypeId id, const_data_ptr_t data, idx_t idx) {
	switch (id) {
	case LogicalTypeId::INTEGER:
		return LoadAsInt64<int32_t>(data, idx);
	case LogicalTypeId::BIGINT:
		return LoadAsInt64<int64_t>(data, idx);
	case LogicalTypeId::UINTEGER:
		return LoadAsInt64<uint32_t>(data, idx);
	case LogicalTypeId::DATE:
		// date_t holds days as int32_t.
		return LoadAsInt64<int32_t>(data, idx);
	default:
		throw InternalException("KeyBitmap: type not bitmap-eligible (should have been gated)");
	}
}

} // namespace

// =============================================================================
// Eligibility — bitmap-path gating used by both the sequential TryBuild and
// the parallel SJBuildBitmapInitEvent dispatch in PhysicalSJBuild::Finalize.
// =============================================================================
KeyBitmap::EligibilityResult KeyBitmap::CheckEligibility(const vector<idx_t> &build_col_ids,
                                                         const vector<LogicalType> &build_col_types) {
	EligibilityResult r {false, 0, LogicalTypeId::INVALID};
	if (build_col_ids.empty() || build_col_ids.size() != build_col_types.size()) {
		return r;
	}
	// v1: single-column only. Composite-key flattening is plan-3 open question 1.
	if (build_col_ids.size() != 1) {
		return r;
	}
	auto type_id = build_col_types[0].id();
	if (!IsBitmapEligibleType(type_id)) {
		return r;
	}
	r.eligible = true;
	r.col_id = build_col_ids[0];
	r.type_id = type_id;
	return r;
}

// =============================================================================
// Per-task min/max scan. FetchChunk-based so calls over disjoint chunk
// ranges have no shared state — the basis of within-filter parallelism.
// =============================================================================
KeyBitmap::MinMaxRange KeyBitmap::ScanMinMaxRange(const ColumnDataCollection &build_data, idx_t col_id,
                                                  LogicalTypeId type_id, idx_t chunk_from, idx_t chunk_to) {
	MinMaxRange r {NumericLimits<int64_t>::Maximum(), NumericLimits<int64_t>::Minimum(), 0};

	DataChunk scan_chunk;
	build_data.InitializeScanChunk(scan_chunk);
	for (idx_t ci = chunk_from; ci < chunk_to; ci++) {
		scan_chunk.Reset();
		build_data.FetchChunk(ci, scan_chunk);
		auto &v = scan_chunk.data[col_id];
		UnifiedVectorFormat format;
		v.ToUnifiedFormat(scan_chunk.size(), format);
		auto data = const_data_ptr_cast(format.data);
		for (idx_t i = 0; i < scan_chunk.size(); i++) {
			auto idx = format.sel->get_index(i);
			if (!format.validity.RowIsValid(idx)) {
				continue;
			}
			int64_t value = LoadKeyAsInt64(type_id, data, idx);
			if (value < r.min_key) {
				r.min_key = value;
			}
			if (value > r.max_key) {
				r.max_key = value;
			}
			r.non_null_rows++;
		}
	}
	return r;
}

KeyBitmap::MinMaxRange KeyBitmap::ReduceMinMax(const vector<MinMaxRange> &locals) {
	MinMaxRange r {NumericLimits<int64_t>::Maximum(), NumericLimits<int64_t>::Minimum(), 0};
	for (const auto &l : locals) {
		r.non_null_rows += l.non_null_rows;
		if (l.non_null_rows == 0) {
			continue;
		}
		if (l.min_key < r.min_key) {
			r.min_key = l.min_key;
		}
		if (l.max_key > r.max_key) {
			r.max_key = l.max_key;
		}
	}
	return r;
}

// =============================================================================
// Allocate — size the bitmap, range-check against budget, zero the storage.
// =============================================================================
unique_ptr<KeyBitmap> KeyBitmap::Allocate(ClientContext &context, const MinMaxRange &range,
                                          const LogicalType &key_type, idx_t byte_budget) {
	if (range.non_null_rows == 0) {
		// Build relation is empty (or all-NULL) — emit a bitmap with zero
		// capacity so the probe correctly filters everything.
		auto bm = make_uniq<KeyBitmap>();
		bm->min_key_ = 0;
		bm->max_key_ = -1;
		bm->bit_count_ = 0;
		bm->pop_count_ = 0;
		bm->key_type_ = key_type;
		return bm;
	}

	// (max - min + 1) bits required. Use uint64_t arithmetic since the
	// range can exceed int64_t bounds in pathological cases.
	uint64_t range_size = static_cast<uint64_t>(range.max_key - range.min_key) + 1ULL;
	uint64_t bytes_needed = (range_size + 7ULL) / 8ULL;
	if (bytes_needed > byte_budget) {
		return nullptr;
	}

	uint64_t words_needed = (range_size + 63ULL) / 64ULL;
	auto bm = make_uniq<KeyBitmap>();
	bm->min_key_ = range.min_key;
	bm->max_key_ = range.max_key;
	bm->bit_count_ = NumericCast<idx_t>(words_needed * 64ULL);
	bm->key_type_ = key_type;

	auto &buffer_manager = BufferManager::GetBufferManager(context);
	auto &allocator = buffer_manager.GetBufferAllocator();
	// Over-allocate by 64 bytes so we can align the start to a cache line.
	bm->buffer_ = allocator.Allocate(words_needed * sizeof(uint64_t) + 64);
	auto raw = reinterpret_cast<uintptr_t>(bm->buffer_.get());
	auto aligned = (raw + 63ULL) & ~63ULL;
	bm->words_ = reinterpret_cast<uint64_t *>(aligned);
	std::memset(bm->words_, 0, words_needed * sizeof(uint64_t));
	return bm;
}

// =============================================================================
// FillBitsRange — per-task bit-set kernel. PARALLEL=true uses
// __atomic_or_fetch (relaxed) so concurrent tasks setting bits in the same
// word are race-free. PARALLEL=false keeps the plain `|=` for the sequential
// TryBuild fast path; the templated form lets both compile to a tight loop.
// =============================================================================
template <bool PARALLEL>
void KeyBitmap::FillBitsRange(const ColumnDataCollection &build_data, idx_t col_id, LogicalTypeId type_id,
                              idx_t chunk_from, idx_t chunk_to) {
	if (bit_count_ == 0) {
		return;
	}
	const int64_t min_key = min_key_;
	uint64_t *__restrict words = words_;

	DataChunk scan_chunk;
	build_data.InitializeScanChunk(scan_chunk);
	for (idx_t ci = chunk_from; ci < chunk_to; ci++) {
		scan_chunk.Reset();
		build_data.FetchChunk(ci, scan_chunk);
		auto &v = scan_chunk.data[col_id];
		UnifiedVectorFormat format;
		v.ToUnifiedFormat(scan_chunk.size(), format);
		auto data = const_data_ptr_cast(format.data);
		for (idx_t i = 0; i < scan_chunk.size(); i++) {
			auto idx = format.sel->get_index(i);
			if (!format.validity.RowIsValid(idx)) {
				continue;
			}
			int64_t value = LoadKeyAsInt64(type_id, data, idx);
			// Guarded by the min/max reduce; bit_idx is always in range.
			uint64_t bit_idx = static_cast<uint64_t>(value - min_key);
			const uint64_t mask = 1ULL << (bit_idx & 63ULL);
			if (PARALLEL) {
				__atomic_or_fetch(&words[bit_idx >> 6], mask, __ATOMIC_RELAXED);
			} else {
				words[bit_idx >> 6] |= mask;
			}
		}
	}
}

// Explicit instantiations — bodies live above so they are visible at the
// instantiation point and the symbol is emitted in this TU.
template void KeyBitmap::FillBitsRange<true>(const ColumnDataCollection &, idx_t, LogicalTypeId, idx_t, idx_t);
template void KeyBitmap::FillBitsRange<false>(const ColumnDataCollection &, idx_t, LogicalTypeId, idx_t, idx_t);

void KeyBitmap::FinalizePopCount() {
	const idx_t words_needed = bit_count_ / 64;
	idx_t pop = 0;
	for (idx_t w = 0; w < words_needed; w++) {
		pop += static_cast<idx_t>(__builtin_popcountll(words_[w]));
	}
	pop_count_ = pop;
}

// =============================================================================
// Sequential entry point — thin wrapper over the helpers above. The parallel
// build path in PhysicalSJBuild::Finalize invokes the helpers individually
// via SJBuildBitmapInitEvent / SJBuildBitmapFillEvent.
// =============================================================================
unique_ptr<KeyBitmap> KeyBitmap::TryBuild(ClientContext &context,
                                          const ColumnDataCollection &build_data,
                                          const vector<idx_t> &build_col_ids,
                                          const vector<LogicalType> &build_col_types,
                                          idx_t byte_budget) {
	auto elig = CheckEligibility(build_col_ids, build_col_types);
	if (!elig.eligible) {
		return nullptr;
	}
	if (byte_budget == 0) {
		// PRAGMA outer_yan_bitmap_max_bytes = 0 forces HashFilter — short-
		// circuit before the (possibly large) min/max scan.
		return nullptr;
	}

	const idx_t chunk_count = build_data.ChunkCount();
	auto range = ScanMinMaxRange(build_data, elig.col_id, elig.type_id, 0, chunk_count);
	auto bm = Allocate(context, range, build_col_types[0], byte_budget);
	if (!bm) {
		return nullptr;
	}
	if (bm->bit_count_ == 0) {
		// Empty build — Allocate already returned the zero-capacity bitmap.
		return bm;
	}
	bm->FillBitsRange<false>(build_data, elig.col_id, elig.type_id, 0, chunk_count);
	bm->FinalizePopCount();
	return bm;
}

bool KeyBitmap::Probe(int64_t flat_key) const {
	if (pop_count_ == 0) {
		return false;
	}
	if (flat_key < min_key_ || flat_key > max_key_) {
		return false;
	}
	uint64_t bit_idx = static_cast<uint64_t>(flat_key - min_key_);
	return (words_[bit_idx >> 6] >> (bit_idx & 63ULL)) & 1ULL;
}

void KeyBitmap::ProbeBatch(const DataChunk &input,
                           const vector<idx_t> &probe_col_ids,
                           SelectionVector &sel, idx_t &approved) const {
	approved = 0;
	if (probe_col_ids.empty()) {
		throw InternalException("KeyBitmap::ProbeBatch: no probe columns");
	}
	if (probe_col_ids.size() != 1) {
		throw InternalException("KeyBitmap::ProbeBatch: composite keys unsupported in v1");
	}
	if (pop_count_ == 0) {
		// Build was empty — no probe row survives.
		return;
	}

	const auto type_id = key_type_.id();
	const auto col_id = probe_col_ids[0];
	auto &v = input.data[col_id];

	UnifiedVectorFormat format;
	v.ToUnifiedFormat(input.size(), format);
	const auto data = const_data_ptr_cast(format.data);

	// Two-pass branchless DuckDB-style kernel. Pass 1 is pure straight-line
	// arithmetic over the row range and auto-vectorises; pass 2 is a gather +
	// AND which is too scattered to SIMDise but is at least branch-free up to
	// the final emit-on-survive store.
	const idx_t n = input.size();
	const bool can_have_null = format.validity.CanHaveNull();
	const int64_t min_key = min_key_;
	const int64_t max_key = max_key_;
	const uint64_t *__restrict words = words_;

	alignas(64) uint64_t bit_idx_buf[STANDARD_VECTOR_SIZE];
	alignas(64) uint8_t ok_buf[STANDARD_VECTOR_SIZE];

	// Pass 1 — derive (valid && in_range) and a safe bit_idx for every row.
	// `bit_idx` is clamped to 0 for masked-out rows so the pass-2 gather is
	// always inside `words_[0 .. bit_count_/64)` and never reads OOB.
	for (idx_t i = 0; i < n; i++) {
		const auto idx = format.sel->get_index_unsafe(i);
		const int64_t value = LoadKeyAsInt64(type_id, data, idx);
		const uint8_t valid = can_have_null ? uint8_t(format.validity.RowIsValidUnsafe(idx)) : uint8_t(1);
		const uint8_t in_range = uint8_t((value >= min_key) & (value <= max_key));
		const uint8_t ok = uint8_t(valid & in_range);
		ok_buf[i] = ok;
		bit_idx_buf[i] = ok ? uint64_t(value - min_key) : uint64_t(0);
	}

	// Pass 2 — gather word, extract bit, emit on (ok & hit). The branch on
	// emit is data-dependent on the result and unavoidable for a compaction
	// store; everything else is straight-line.
	for (idx_t i = 0; i < n; i++) {
		const uint64_t bi = bit_idx_buf[i];
		const uint64_t hit = (words[bi >> 6] >> (bi & 63ULL)) & 1ULL;
		if (hit & ok_buf[i]) {
			sel.set_index(approved++, i);
		}
	}
}

} // namespace duckdb
