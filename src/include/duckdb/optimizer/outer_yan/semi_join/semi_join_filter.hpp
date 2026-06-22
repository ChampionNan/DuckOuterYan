//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/semi_join_filter.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/shared_ptr.hpp"
#include "duckdb/common/unique_ptr.hpp"
#include "duckdb/common/vector.hpp"

namespace duckdb {

class KeyBitmap;
class HashFilter;

// =============================================================================
// SemiJoinFilter — tagged-union carrier between SJBuild and SJProbe.
// =============================================================================
//
// Plan 3 contract. At the logical level both `LogicalSJBuild::sj_to_create`
// and `LogicalSJProbe::sj_to_use` hold `vector<shared_ptr<SemiJoinFilter>>`
// pointing at the same instances. That shared_ptr identity does NOT survive
// plan Copy/Serialize/Deserialize (statement verification, plan caching),
// so the durable build↔probe binding is a stable integer `filter_id` carried
// on the logical ops; at physical planning PhysicalPlanGenerator resolves one
// runtime SemiJoinFilter per id (GetOrCreateSJFilter) and re-derives the
// probe's related-build dependency from those ids (LinkSemiJoinProbes).
//
// `kind` is set ONCE by `PhysicalSJBuild::Finalize`. SemijoinInsertion pins
// every filter to HASH (ForceHash) so the kind is type-stable and the probe
// never has to handle a bitmap/undecided case — the probe path branches once
// on `kind` outside the per-tuple loop, and treats UNDECIDED as a hard error.
//
// Cross-thread visibility of the kind / payload writes is handled by the
// DuckDB pipeline scheduler: the probe pipeline depends on the build
// pipeline's Finalize (via PhysicalSJBuild::BuildPipelinesFromRelated ->
// AddDependency), and the event/task graph establishes a happens-before
// edge between Finalize completing and the first probe call. So no
// atomic / memory-order plumbing is needed on this struct.
class SemiJoinFilter {
public:
	enum class Kind : uint8_t { UNDECIDED, BITMAP, HASH };

	SemiJoinFilter();
	~SemiJoinFilter();

	// Lifecycle. Set once at Finalize.
	Kind kind() const {
		return kind_;
	}
	bool finalized() const {
		return kind_ != Kind::UNDECIDED;
	}

	void FinalizeAsBitmap(unique_ptr<KeyBitmap> b);
	// `reason` is a static string describing why the hash kernel was chosen
	// (force_hash / budget0 / ineligible / overflow). It is only consumed by
	// the opt-in DUCKDB_SJ_KERNEL_TRACE diagnostic; pass a literal at the call
	// site that decides the kernel.
	void FinalizeAsHash(shared_ptr<HashFilter> h, const char *reason = "unknown");

	const KeyBitmap &bitmap() const;
	HashFilter &hash() const;
	// Shared-ptr accessor for HashFilterUseKernel::filter, which takes a
	// shared_ptr<HashFilter>. Only valid when kind() == HASH.
	shared_ptr<HashFilter> hash_shared() const;

	// True iff the build set is empty (no probe row survives).
	bool IsEmpty() const;

	// Plan-time hint: when true, PhysicalSJBuild::Finalize skips
	// KeyBitmap::TryBuild and builds a HashFilter directly. Set by
	// SemijoinInsertion when `outer_yan_stats_prefilter` is on AND base-table
	// stats for the build key predict the bitmap range would exceed the byte
	// budget. The runtime overflow check inside TryBuild remains the
	// correctness guarantee; this flag only avoids a wasted min/max scan.
	void ForceHash() {
		force_hash_ = true;
	}
	bool force_hash() const {
		return force_hash_;
	}

private:
	Kind kind_;
	unique_ptr<KeyBitmap> bitmap_;
	shared_ptr<HashFilter> hash_;
	bool force_hash_ = false;
};

} // namespace duckdb
