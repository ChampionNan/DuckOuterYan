#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_post.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/common/to_string.hpp"
#include "duckdb/execution/operator/join/physical_sj_build.hpp"
#include "duckdb/main/client_config.hpp"
#include "duckdb/main/client_context.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_trace.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"

#include <chrono>

namespace duckdb {

OuterYanPost::OuterYanPost(ClientContext &context_p) : context(context_p) {
}

unique_ptr<LogicalOperator> OuterYanPost::Optimize(OuterYanTree &tree) {
	if (!tree.HasOJT()) {
		throw InternalException("OuterYanPost::Optimize: tree has no OJT");
	}

	// Pipeline: Resimplify → PartialReduction → MarkAggPushdown → OJTToLogicalPlan →
	// SemijoinInsertOnPlan. Aggregation-driven root anchoring is already
	// enforced by OuterYanDP, so the OJT seen here is order-correct.
	using Clock = std::chrono::steady_clock;
	auto phase_start = Clock::now();
	Resimplify(tree);
	tree.phase_timings.resimplification +=
	    std::chrono::duration<double>(Clock::now() - phase_start).count();
	if (OuterYanTrace::Enabled()) {
		OuterYanTrace::Stage("after Resimplify (" + to_string(tree.stage_stats.resimplify_reverts) +
		                         " revert(s); OJT)",
		                     tree.OJT().PrintAsTree(true));
	}
	phase_start = Clock::now();
	if (IsPartialReductionEnabled(context)) {
		PartialReduction().Apply(tree);
	}
	tree.phase_timings.semijoin_pair_planning +=
	    std::chrono::duration<double>(Clock::now() - phase_start).count();

	// Record the per-edge aggregate-pushdown gate while the OJT is still
	// live. Must run before OJTToLogicalPlan because the marker reads
	// `OJTEdge::has_pk_fk_constraint` / `parent_relation_id` / `order` off
	// the OJT.
	phase_start = Clock::now();
	MarkAggPushdown(tree);
	tree.phase_timings.aggregate_pushdown_marking +=
	    std::chrono::duration<double>(Clock::now() - phase_start).count();

	// Lower the OJT to a fresh LogicalPlan. After this call, `tree.ojt` and
	// `tree.source_plan` are released — only `tree.{bottom_up_pairs,
	// top_down_pairs, table_to_relation, agg_pushdown_decisions}` remain
	// valid for SJ insertion and downstream aggregate pushdown.
	phase_start = Clock::now();
	auto plan = tree.OJTToLogicalPlan(context);
	tree.phase_timings.plan_lowering +=
	    std::chrono::duration<double>(Clock::now() - phase_start).count();

	// Final pass: splice LogicalSJBuild + LogicalSJProbe wraps based on the
	// pre-decided pairs. Plan 3 contract — runs on the rebuilt LogicalPlan,
	// not on the OJT.
	phase_start = Clock::now();
	plan = SemijoinInsertOnPlan(std::move(plan), tree);
	tree.phase_timings.semijoin_insertion +=
	    std::chrono::duration<double>(Clock::now() - phase_start).count();
	if (OuterYanTrace::Enabled()) {
		OuterYanTrace::Stage("after semi-join insertion (logical plan)", plan->ToString());
	}

	return plan;
}

void OuterYanPost::Resimplify(OuterYanTree &tree) {
	if (!tree.HasOJT()) {
		throw InternalException("OuterYanPost::Resimplify: tree has no OJT");
	}
	resimplification.Apply(tree.OJT());
	tree.stage_stats.resimplify_reverts += resimplification.reverts;
}

void OuterYanPost::MarkAggPushdown(OuterYanTree &tree) {
	if (!tree.HasOJT()) {
		throw InternalException("OuterYanPost::MarkAggPushdown: tree has no OJT");
	}
	agg_pushdown.Apply(tree);
}

unique_ptr<LogicalOperator> OuterYanPost::SemijoinInsertOnPlan(unique_ptr<LogicalOperator> plan,
                                                               const OuterYanTree &tree) {
	const bool prefilter_enabled = IsStatsPrefilterEnabled(context);
	const idx_t bitmap_budget = PhysicalSJBuild::GetBitmapBudget(context);
	return semijoin_insertion.Apply(std::move(plan), tree, context, bitmap_budget, prefilter_enabled);
}

bool OuterYanPost::IsStatsPrefilterEnabled(ClientContext &context) {
	auto &cfg = ClientConfig::GetConfig(context);
	auto it = cfg.user_variables.find(kStatsPrefilterVar);
	// NOTE: ← flip to `true` to enable by default
	if (it == cfg.user_variables.end() || it->second.IsNull()) {
		return false;
	}
	try {
		return it->second.DefaultCastAs(LogicalType::BOOLEAN).GetValue<bool>();
	} catch (...) {
		throw InvalidInputException("SET VARIABLE %s must be a boolean (got %s)", kStatsPrefilterVar,
		                            it->second.ToString());
	}
}

bool OuterYanPost::IsPartialReductionEnabled(ClientContext &context) {
	auto &variables = ClientConfig::GetConfig(context).user_variables;
	auto entry = variables.find(kPartialReductionVar);
	if (entry == variables.end() || entry->second.IsNull()) {
		return true;
	}
	try {
		return entry->second.DefaultCastAs(LogicalType::BOOLEAN).GetValue<bool>();
	} catch (...) {
		throw InvalidInputException("SET VARIABLE %s must be a boolean", kPartialReductionVar);
	}
}

} // namespace duckdb
