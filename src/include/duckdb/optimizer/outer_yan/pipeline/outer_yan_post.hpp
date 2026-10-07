//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/pipeline/outer_yan_post.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/optimizer/outer_yan/pipeline/agg_pushdown.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/resimplification.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/partial_reduction.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/semijoin_insertion.hpp"
#include "duckdb/planner/logical_operator.hpp"

namespace duckdb {
class ClientContext;

//! OuterYanPost — third OuterYan pass (runs after OuterYanDP).
//!
//! `Optimize` consumes the OJT produced by OuterYanDP, runs the OJT-stage
//! transforms, records the aggregate-pushdown decision vector, lowers to
//! LogicalPlan via OJTToLogicalPlan, and as a final step splices in
//! LogicalSJBuild / LogicalSJProbe operators based on the pre-decided pair
//! lists on `OuterYanTree`.
//!
//! Step order:
//!   1. Resimplify           — outer→original via arrow-side + eval-order.
//!   2. MarkAggPushdown      — record per-edge `OuterYanAggPushdownDecision`
//!                             on the OJT (Slice 1 of plan 4: relation-level
//!                             PK-FK gate; threshold check deferred to the
//!                             plan-side `AggregatePushdownOuter`).
//!   3. OJTToLogicalPlan     — (shared utility) rebuild the LogicalPlan.
//!   4. SemijoinInsertOnPlan — wrap LogicalGets with SJBuild + SJProbe.
//!
//! The former `OrderFixApply` step is gone: aggregation-driven root anchoring
//! is now enforced upstream by `OuterYanDP` (`FIX_ALL_OUTPUTS` /
//! `FIX_ONE_OUTPUT` regimes), so the OJT handed to this pass already carries
//! the correct evaluation order.
//!
//! Skipped entirely when the OuterYan-active flag is false.
class OuterYanPost {
public:
	explicit OuterYanPost(ClientContext &context);

	//! Consumes `tree.ojt`, runs OJT-stage transforms, lowers via
	//! `OJTToLogicalPlan`, then splices SJ operators onto the rebuilt
	//! LogicalPlan. Returns the rebuilt + spliced plan.
	unique_ptr<LogicalOperator> Optimize(OuterYanTree &tree);

	void Resimplify(OuterYanTree &tree);
	//! Populate `tree.agg_pushdown_decisions` for later consumption by
	//! `AggregatePushdownOuter` on the rebuilt plan.
	void MarkAggPushdown(OuterYanTree &tree);
	//! Splice LogicalSJBuild / LogicalSJProbe onto the rebuilt LogicalPlan
	//! using `tree.{bottom_up_pairs, top_down_pairs}`. Plan 3 contract — the
	//! pass runs on the rebuilt plan, not on the OJT.
	unique_ptr<LogicalOperator> SemijoinInsertOnPlan(unique_ptr<LogicalOperator> plan, const OuterYanTree &tree);

	//! Per-session knob for the stats-prefilter optimization. Read at the
	//! start of SemijoinInsertOnPlan; when true, base-table min/max for each
	//! fresh SemiJoinFilter's single-column build key is checked against the
	//! bitmap byte budget, and the filter is tagged ForceHash on predicted
	//! overflow. Default false — base-table stats over a heavily-filtered
	//! table can over-estimate the post-filter range and wrongly skip the
	//! bitmap path.
	//!   SET VARIABLE outer_yan_stats_prefilter = true;
	static constexpr const char *kStatsPrefilterVar = "outer_yan_stats_prefilter";
	static bool IsStatsPrefilterEnabled(ClientContext &context);
	//! A/B escape hatch for guarded, order-aware reduction (default enabled).
	static constexpr const char *kPartialReductionVar = "outer_yan_partial_reduction";
	static bool IsPartialReductionEnabled(ClientContext &context);

private:
	ClientContext &context;
	Resimplification resimplification;
	SemijoinInsertion semijoin_insertion;
	AggPushdown agg_pushdown;
};

} // namespace duckdb
