#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_optimizer.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/main/client_context.hpp"
#include "duckdb/optimizer/join_order/join_order_optimizer.hpp"
#include "duckdb/optimizer/optimizer.hpp"
#include "duckdb/optimizer/outer_join_simplification.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_trace.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/aggregate_pushdown_outer.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_dp.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_post.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_pre.hpp"

#include <cmath>
#include <iomanip>
#include <sstream>

namespace duckdb {

OuterYanOptimizer::OuterYanOptimizer(Optimizer &optimizer_p)
    : optimizer(optimizer_p), context(optimizer_p.context) {
}

OuterYanOptimizationResult OuterYanOptimizer::Optimize(unique_ptr<LogicalOperator> input) {
	OuterYanOptimizationResult result;
	if (!input) {
		throw InternalException("OuterYanOptimizer::Optimize: null input plan");
	}

	OuterYanTree candidate_tree;
	unique_ptr<LogicalOperator> explain_wrapper;
	unique_ptr<LogicalOperator> baseline_plan;
	bool applicable = false;

	optimizer.RunOptimizer(OptimizerType::OUTER_YAN_PRE, [&]() {
		// Applicability must inspect the real plan inside EXPLAIN, but an
		// inapplicable plan is left attached and untouched for the normal path.
		LogicalOperator *candidate_input = input.get();
		if (input->type == LogicalOperatorType::LOGICAL_EXPLAIN && input->children.size() == 1) {
			candidate_input = input->children[0].get();
		}
		applicable = candidate_tree.CheckApplicability(*candidate_input);
		if (!applicable) {
			return;
		}

		unique_ptr<LogicalOperator> working_plan;
		if (input->type == LogicalOperatorType::LOGICAL_EXPLAIN) {
			explain_wrapper = std::move(input);
			working_plan = std::move(explain_wrapper->children[0]);
		} else {
			working_plan = std::move(input);
		}

		// Both candidates start from this exact post-filter-pushdown plan.
		baseline_plan = working_plan->Copy(context);
		if (OuterYanTrace::Enabled()) {
			OuterYanTrace::BeginQuery(context.GetCurrentQuery());
			OuterYanTrace::Stage("input logical plan (pre-OuterYan)", working_plan->ToString());
		}
		OuterYanPre().Optimize(std::move(working_plan), candidate_tree);
	});

	if (!applicable) {
		OuterYanTrace::Decision(false, false, false, "INAPPLICABLE");
		result.plan = std::move(input);
		return result;
	}

	OuterYanDPCostSummary candidate_cost;
	optimizer.RunOptimizer(OptimizerType::OUTER_YAN_DP, [&]() {
		OuterYanDP dp(context);
		candidate_cost = dp.Optimize(candidate_tree);
	});

	// Produce the actual normal DuckDB alternative, rather than comparing the
	// DP result with OuterYan's own pre-DP input shape.
	optimizer.RunOptimizer(OptimizerType::OUTER_JOIN_SIMPLIFICATION, [&]() {
		OuterJoinSimplification simplification;
		simplification.VisitOperator(*baseline_plan);
	});
	optimizer.RunOptimizer(OptimizerType::JOIN_ORDER, [&]() {
		JoinOrderOptimizer join_order(context);
		baseline_plan = join_order.Optimize(std::move(baseline_plan));
	});
	if (OuterYanTrace::Enabled()) {
		OuterYanTrace::Stage("normal DuckDB candidate (logical plan)", baseline_plan->ToString());
	}

	// This copy is metadata only. It preserves the selected baseline plan while
	// giving shape comparison, common cost scoring, and aggregate pushdown a
	// tree whose positional decisions match the baseline's own join order.
	OuterYanTree baseline_tree;
	baseline_tree.BuildOT(baseline_plan->Copy(context));
	const auto candidate_signature = OuterYanDP::JoinGroupingSignature(candidate_tree);
	const auto baseline_signature = OuterYanDP::JoinGroupingSignature(baseline_tree);
	const bool outer_reordered = candidate_cost.has_complete_plan &&
	                             candidate_signature != baseline_signature;

	bool cost_gate_applied = false;
	bool outer_yan_selected = false;
	const char *reason = "OUTERYAN_FAILED";
	OuterYanDecisionCosts trace_costs;
	if (candidate_cost.has_complete_plan) {
		OuterYanDP baseline_scorer(context);
		trace_costs.baseline_cost = baseline_scorer.ScoreCurrentJoinTree(baseline_tree);
		trace_costs.candidate_join_cost = candidate_cost.chosen_real_join_cost;
		trace_costs.semijoin_raw_cost = candidate_cost.SemijoinRawCost();
		trace_costs.semijoin_cost_ratio = SEMIJOIN_COST_RATIO;
		trace_costs.weighted_semijoin_cost = SEMIJOIN_COST_RATIO * trace_costs.semijoin_raw_cost;
		trace_costs.candidate_total = candidate_cost.CandidateCost(SEMIJOIN_COST_RATIO);
		trace_costs.cost_ratio_limit = MAX_CANDIDATE_TO_BASELINE_RATIO;
		trace_costs.baseline_threshold = MAX_CANDIDATE_TO_BASELINE_RATIO * trace_costs.baseline_cost;
		trace_costs.round1_build = candidate_cost.round1_build_cost;
		trace_costs.round1_probe = candidate_cost.round1_probe_cost;
		trace_costs.round2_build = candidate_cost.round2_build_cost;
		trace_costs.round2_probe = candidate_cost.round2_probe_cost;
		trace_costs.available = std::isfinite(trace_costs.baseline_cost) &&
		                        std::isfinite(trace_costs.candidate_join_cost) &&
		                        std::isfinite(trace_costs.semijoin_raw_cost) &&
		                        std::isfinite(trace_costs.semijoin_cost_ratio) &&
		                        std::isfinite(trace_costs.weighted_semijoin_cost) &&
		                        std::isfinite(trace_costs.candidate_total) &&
		                        std::isfinite(trace_costs.baseline_threshold);
	}

	if (candidate_cost.has_complete_plan && !outer_reordered) {
		reason = "DUCKDB_PLAN";
	} else if (candidate_cost.has_complete_plan && !APPLY_COST_GATE) {
		outer_yan_selected = true;
		reason = "ALWAYS_OUTERYAN";
	} else if (candidate_cost.has_complete_plan && APPLY_COST_GATE) {
		if (trace_costs.available) {
			cost_gate_applied = true;
			outer_yan_selected = trace_costs.candidate_total <= trace_costs.baseline_threshold;
			reason = outer_yan_selected ? "COST_OUTERYAN_BETTER" : "COST_DUCKDB_BETTER";
		} else {
			reason = "COST_UNAVAILABLE";
		}
	}
	candidate_tree.stage_stats.outer_reordered = outer_reordered;
	candidate_tree.stage_stats.cost_gate_applied = cost_gate_applied;
	candidate_tree.stage_stats.outer_yan_selected = outer_yan_selected;

	if (OuterYanTrace::Enabled()) {
		std::ostringstream costs;
		costs << std::setprecision(17)
		      << "apply_cost_gate=" << (APPLY_COST_GATE ? 1 : 0) << "\n"
		      << "baseline_cost=" << trace_costs.baseline_cost << "\n"
		      << "candidate_join_cost=" << trace_costs.candidate_join_cost << "\n"
		      << "semijoin_raw_cost=" << trace_costs.semijoin_raw_cost << "\n"
		      << "semijoin_cost_ratio=" << std::setprecision(6) << trace_costs.semijoin_cost_ratio << "\n"
		      << std::setprecision(17)
		      << "weighted_semijoin_cost=" << trace_costs.weighted_semijoin_cost << "\n"
		      << "  round1_build=" << trace_costs.round1_build << "\n"
		      << "  round1_probe=" << trace_costs.round1_probe << "\n"
		      << "  round2_build=" << trace_costs.round2_build << "\n"
		      << "  round2_probe=" << trace_costs.round2_probe << "\n"
		      << "candidate_total=" << trace_costs.candidate_total << "\n"
		      << "cost_ratio_limit=" << std::setprecision(6) << trace_costs.cost_ratio_limit << "\n"
		      << std::setprecision(17)
		      << "baseline_threshold=" << trace_costs.baseline_threshold << "\n"
		      << "cost_gate_formula=candidate_join_cost + semijoin_cost_ratio * semijoin_raw_cost <= "
		         "cost_ratio_limit * baseline_cost\n"
		      << "cost_gate_values=" << trace_costs.candidate_join_cost << " + " << std::setprecision(6)
		      << trace_costs.semijoin_cost_ratio << std::setprecision(17) << " * " << trace_costs.semijoin_raw_cost
		      << " <= " << std::setprecision(6) << trace_costs.cost_ratio_limit << std::setprecision(17) << " * "
		      << trace_costs.baseline_cost << "\n"
		      << "cost_gate_result=" << trace_costs.candidate_total << " <= " << trace_costs.baseline_threshold << " => "
		      << (trace_costs.available && trace_costs.candidate_total <= trace_costs.baseline_threshold ? "PASS"
		                                                                                                    : "FAIL")
		      << "\n";
		OuterYanTrace::Stage("candidate cost comparison", costs.str());
	}
	OuterYanTrace::Decision(outer_reordered, cost_gate_applied, outer_yan_selected, reason, trace_costs);

	unique_ptr<LogicalOperator> selected_plan;
	OuterYanTree *selected_tree;
	if (outer_yan_selected) {
		optimizer.RunOptimizer(OptimizerType::OUTER_YAN_POST, [&]() {
			OuterYanPost post(context);
			selected_plan = post.Optimize(candidate_tree);
		});
		selected_tree = &candidate_tree;
	} else {
		// Generate aggregate-pushdown decisions from the baseline shape itself.
		// Reusing candidate_tree here is unsafe because the decision vector is
		// consumed positionally during a post-order logical-plan walk.
		baseline_tree.BuildOJT();
		OuterYanPost baseline_post(context);
		baseline_post.MarkAggPushdown(baseline_tree);
		selected_plan = std::move(baseline_plan);
		selected_tree = &baseline_tree;
	}

	// This phase is deliberately outside the candidate branch: both an
	// accepted OuterYan plan and a selected DuckDB baseline receive it, with
	// metadata from the corresponding tree.
	optimizer.RunOptimizer(OptimizerType::AGGREGATE_PUSHDOWN_OUTER, [&]() {
		AggregatePushdownOuter aggregate_pushdown(optimizer, *selected_tree);
		selected_plan = aggregate_pushdown.Optimize(std::move(selected_plan));
		if (OuterYanTrace::Enabled()) {
			OuterYanTrace::Stage("selected plan after Aggregate Pushdown", selected_plan->ToString());
		}
	});
	// The selected plan lives locally while the facade is running, so the
	// normal RunOptimizer post-callback check cannot see it through
	// Optimizer::plan. Preserve the same verification boundary explicitly.
	optimizer.Verify(*selected_plan);

	if (explain_wrapper) {
		explain_wrapper->children[0] = std::move(selected_plan);
		selected_plan = std::move(explain_wrapper);
	}
	result.plan = std::move(selected_plan);
	result.outer_yan_applied = true;
	return result;
}

} // namespace duckdb
