#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_optimizer.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/main/client_context.hpp"
#include "duckdb/optimizer/empty_result_pullup.hpp"
#include "duckdb/optimizer/join_order/join_order_optimizer.hpp"
#include "duckdb/optimizer/optimizer.hpp"
#include "duckdb/optimizer/outer_join_simplification.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_trace.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/aggregate_pushdown_outer.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_dp.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_post.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_pre.hpp"
#include "duckdb/optimizer/statistics_propagator.hpp"

#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <sstream>

namespace duckdb {

namespace {

struct PlanWorkSummary {
	idx_t real_join_count = 0;
	idx_t empty_result_count = 0;
};

struct BaselineEmptyProof {
	bool eliminates_all_join_work = false;
	PlanWorkSummary before;
	PlanWorkSummary after;
	string proof_plan;
};

bool ContainsAggregateLikeOperator(const LogicalOperator &op) {
	if (op.type == LogicalOperatorType::LOGICAL_AGGREGATE_AND_GROUP_BY ||
	    op.type == LogicalOperatorType::LOGICAL_DISTINCT) {
		return true;
	}
	for (const auto &child : op.children) {
		if (ContainsAggregateLikeOperator(*child)) {
			return true;
		}
	}
	return false;
}

bool IsRealJoin(LogicalOperatorType type) {
	switch (type) {
	case LogicalOperatorType::LOGICAL_COMPARISON_JOIN:
	case LogicalOperatorType::LOGICAL_ANY_JOIN:
	case LogicalOperatorType::LOGICAL_DELIM_JOIN:
	case LogicalOperatorType::LOGICAL_ASOF_JOIN:
	case LogicalOperatorType::LOGICAL_POSITIONAL_JOIN:
	case LogicalOperatorType::LOGICAL_CROSS_PRODUCT:
		return true;
	default:
		return false;
	}
}

void SummarizePlanWork(const LogicalOperator &op, PlanWorkSummary &summary) {
	if (IsRealJoin(op.type)) {
		summary.real_join_count++;
	}
	if (op.type == LogicalOperatorType::LOGICAL_EMPTY_RESULT) {
		summary.empty_result_count++;
	}
	for (auto &child : op.children) {
		SummarizePlanWork(*child, summary);
	}
}

BaselineEmptyProof ProveBaselineEliminatesJoinWork(Optimizer &optimizer, ClientContext &context,
                                                   const LogicalOperator &baseline_plan) {
	BaselineEmptyProof result;
	SummarizePlanWork(baseline_plan, result.before);
	auto proof_plan = baseline_plan.Copy(context);
	StatisticsPropagator propagator(optimizer, *proof_plan);
	propagator.PropagateStatistics(proof_plan);
	EmptyResultPullup empty_result_pullup;
	proof_plan = empty_result_pullup.Optimize(std::move(proof_plan));
	SummarizePlanWork(*proof_plan, result.after);
	result.eliminates_all_join_work = result.before.real_join_count > 0 &&
	                                  result.after.empty_result_count > 0 &&
	                                  result.after.real_join_count == 0;
	result.proof_plan = proof_plan->ToString();
	return result;
}

string TableList(const vector<idx_t> &tables) {
	std::ostringstream result;
	for (idx_t i = 0; i < tables.size(); i++) {
		if (i > 0) {
			result << "+";
		}
		result << tables[i];
	}
	return result.str();
}

string FormatJoinCostBreakdown(const char *plan, const OuterYanJoinCostBreakdown &breakdown) {
	std::ostringstream out;
	out << std::setprecision(17);
	for (auto &step : breakdown.steps) {
		out << "[OY_JOIN_COST] plan=" << plan << " step=" << step.step
		    << " kind=" << JoinTypeToString(step.join_kind)
		    << " left_tables=" << TableList(step.left_table_indexes)
		    << " right_tables=" << TableList(step.right_table_indexes)
		    << " output_tables=" << TableList(step.output_table_indexes)
		    << " left_cardinality=" << step.left_cardinality
		    << " right_cardinality=" << step.right_cardinality
		    << " left_distinct=" << step.left_distinct
		    << " right_distinct=" << step.right_distinct
		    << " inner=" << step.inner
		    << " unmatched_left=" << step.unmatched_left
		    << " unmatched_right=" << step.unmatched_right
		    << " output=" << step.output
		    << " local_cost=" << step.local_cost
		    << " subtree_cost=" << step.subtree_cost << "\n";
	}
	out << "[OY_JOIN_COST_TOTAL] plan=" << plan << " root_cardinality=" << breakdown.root_cardinality
	    << " total_cost=" << breakdown.total_cost << "\n";
	return out.str();
}

string FormatSemijoinCostBreakdown(const OuterYanDPCostSummary &summary) {
	std::ostringstream out;
	out << std::setprecision(17);
	for (auto &step : summary.semijoin_steps) {
		out << "[OY_SJ_COST] round=" << step.round << " step=" << step.step
		    << " build_relation=" << step.build_relation << " probe_relation=" << step.probe_relation
		    << " build_table=" << step.build_table_index << " probe_table=" << step.probe_table_index
		    << " filter_reused=" << (step.filter_reused ? 1 : 0)
		    << " build_cardinality=" << step.build_cardinality
		    << " probe_before=" << step.probe_cardinality_before
		    << " build_distinct=" << step.build_distinct
		    << " probe_distinct=" << step.probe_distinct << " survival=" << step.survival
		    << " probe_after=" << step.probe_cardinality_after
		    << " materialize_cost=" << step.materialize_cost
		    << " filter_build_cost=" << step.filter_build_cost << " replay_cost=" << step.replay_cost
		    << " lookup_cost=" << step.lookup_cost << " emit_cost=" << step.emit_cost << "\n";
	}
	return out.str();
}

bool ValidCost(double value) {
	return std::isfinite(value) && value >= 0.0;
}

const char *SelectionModeToString(OuterYanOptimizer::SelectionMode mode) {
	switch (mode) {
	case OuterYanOptimizer::SelectionMode::GATED:
		return "GATED";
	case OuterYanOptimizer::SelectionMode::FORCE_OUTERYAN:
		return "FORCE_OUTERYAN";
	}
	return "UNKNOWN";
}

bool ForceCandidateForCorrectnessValidation() {
	const auto value = std::getenv("DUCKDB_OY_FORCE_CANDIDATE");
	return value && value[0] == '1' && value[1] == '\0';
}

} // namespace

OuterYanOptimizer::OuterYanOptimizer(Optimizer &optimizer_p)
    : optimizer(optimizer_p), context(optimizer_p.context) {
}

OuterYanOptimizationResult OuterYanOptimizer::Optimize(unique_ptr<LogicalOperator> input) {
	OuterYanOptimizationResult result;
	if (!input) {
		throw InternalException("OuterYanOptimizer::Optimize: null input plan");
	}
	const bool force_candidate_for_validation = ForceCandidateForCorrectnessValidation();
	const auto selection_mode =
	    force_candidate_for_validation ? "FORCE_OUTERYAN_DIAGNOSTIC" : SelectionModeToString(SELECTION_MODE);
	const bool apply_cost_gate = APPLY_COST_GATE && !force_candidate_for_validation;

	OuterYanTree candidate_tree;
	unique_ptr<LogicalOperator> explain_wrapper;
	unique_ptr<LogicalOperator> baseline_plan;
	bool applicable = false;
	bool contains_aggregate = false;

	optimizer.RunOptimizer(OptimizerType::OUTER_YAN_PRE, [&]() {
		// Applicability must inspect the real plan inside EXPLAIN, but an
		// inapplicable plan is left attached and untouched for the normal path.
		LogicalOperator *candidate_input = input.get();
		if (input->type == LogicalOperatorType::LOGICAL_EXPLAIN && input->children.size() == 1) {
			candidate_input = input->children[0].get();
		}
		contains_aggregate = ContainsAggregateLikeOperator(*candidate_input);
		if (contains_aggregate) {
			return;
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
		OuterYanDecisionRecord decision;
		decision.selection_mode = selection_mode;
		decision.reason = contains_aggregate ? "DUCKDB_AGGREGATE" : "INAPPLICABLE";
		OuterYanTrace::Decision(decision);
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
	const auto empty_proof = ProveBaselineEliminatesJoinWork(optimizer, context, *baseline_plan);
	if (OuterYanTrace::Enabled()) {
		std::ostringstream proof;
		proof << "before_real_joins=" << empty_proof.before.real_join_count << "\n"
		      << "before_empty_results=" << empty_proof.before.empty_result_count << "\n"
		      << "after_real_joins=" << empty_proof.after.real_join_count << "\n"
		      << "after_empty_results=" << empty_proof.after.empty_result_count << "\n"
		      << "eliminates_all_join_work=" << (empty_proof.eliminates_all_join_work ? 1 : 0) << "\n"
		      << empty_proof.proof_plan;
		OuterYanTrace::Stage("DuckDB baseline empty-result proof", proof.str());
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

	OuterYanDecisionCosts trace_costs;
	OuterYanJoinCostBreakdown baseline_breakdown;
	if (candidate_cost.has_complete_plan) {
		OuterYanDP baseline_scorer(context, candidate_cost.parameters);
		baseline_breakdown = baseline_scorer.ScoreCurrentJoinTreeDetailed(baseline_tree);
		trace_costs.baseline_cost = baseline_breakdown.total_cost;
		trace_costs.candidate_join_cost = candidate_cost.candidate_join_breakdown.total_cost;
		trace_costs.semijoin_raw_cost = candidate_cost.SemijoinRawCost();
		trace_costs.semijoin_cost_ratio = SEMIJOIN_COST_RATIO;
		trace_costs.weighted_semijoin_cost = SEMIJOIN_COST_RATIO * trace_costs.semijoin_raw_cost;
		trace_costs.candidate_total = trace_costs.candidate_join_cost + trace_costs.weighted_semijoin_cost;
		trace_costs.cost_ratio_limit = MAX_CANDIDATE_TO_BASELINE_RATIO;
		trace_costs.baseline_threshold = MAX_CANDIDATE_TO_BASELINE_RATIO * trace_costs.baseline_cost;
		trace_costs.round1_build = candidate_cost.round1_build_cost;
		trace_costs.round1_probe = candidate_cost.round1_probe_cost;
		trace_costs.round2_build = candidate_cost.round2_build_cost;
		trace_costs.round2_probe = candidate_cost.round2_probe_cost;
		for (const auto &step : candidate_cost.semijoin_steps) {
			if (step.round == 1) {
				trace_costs.round1_pairs++;
				trace_costs.round1_filters += step.filter_reused ? 0 : 1;
			} else if (step.round == 2) {
				trace_costs.round2_pairs++;
				trace_costs.round2_filters += step.filter_reused ? 0 : 1;
			} else {
				throw InternalException("OuterYan semi-join cost step has invalid round %llu", step.round);
			}
		}
		trace_costs.raw_cost_delta = trace_costs.candidate_total - trace_costs.baseline_cost;
		trace_costs.gate_lhs = trace_costs.candidate_total;
		trace_costs.gate_rhs = trace_costs.baseline_threshold;
		trace_costs.gate_margin = trace_costs.gate_rhs - trace_costs.gate_lhs;
		if (trace_costs.baseline_cost > 0.0) {
			trace_costs.raw_cost_ratio = trace_costs.candidate_total / trace_costs.baseline_cost;
			trace_costs.raw_cost_ratio_available = true;
		}
		trace_costs.inner_output_weight = candidate_cost.parameters.inner_output_weight;
		trace_costs.unmatched_left_weight = candidate_cost.parameters.unmatched_left_weight;
		trace_costs.unmatched_right_weight = candidate_cost.parameters.unmatched_right_weight;
		trace_costs.semijoin_materialize_weight = candidate_cost.parameters.semijoin_materialize_weight;
		trace_costs.semijoin_filter_build_weight = candidate_cost.parameters.semijoin_filter_build_weight;
		trace_costs.semijoin_replay_weight = candidate_cost.parameters.semijoin_replay_weight;
		trace_costs.semijoin_probe_lookup_weight = candidate_cost.parameters.semijoin_probe_lookup_weight;
		trace_costs.semijoin_probe_emit_weight = candidate_cost.parameters.semijoin_probe_emit_weight;
		trace_costs.available =
		    ValidCost(trace_costs.baseline_cost) && ValidCost(trace_costs.candidate_join_cost) &&
		    ValidCost(trace_costs.semijoin_raw_cost) && ValidCost(trace_costs.semijoin_cost_ratio) &&
		    ValidCost(trace_costs.weighted_semijoin_cost) && ValidCost(trace_costs.candidate_total) &&
		    ValidCost(trace_costs.cost_ratio_limit) && ValidCost(trace_costs.baseline_threshold) &&
		    ValidCost(trace_costs.round1_build) && ValidCost(trace_costs.round1_probe) &&
		    ValidCost(trace_costs.round2_build) && ValidCost(trace_costs.round2_probe) &&
		    ValidCost(trace_costs.inner_output_weight) && ValidCost(trace_costs.unmatched_left_weight) &&
		    ValidCost(trace_costs.unmatched_right_weight) &&
		    ValidCost(trace_costs.semijoin_materialize_weight) &&
		    ValidCost(trace_costs.semijoin_filter_build_weight) &&
		    ValidCost(trace_costs.semijoin_replay_weight) &&
		    ValidCost(trace_costs.semijoin_probe_lookup_weight) &&
		    ValidCost(trace_costs.semijoin_probe_emit_weight) &&
		    std::isfinite(trace_costs.raw_cost_delta) && std::isfinite(trace_costs.gate_margin) &&
		    (!trace_costs.raw_cost_ratio_available || std::isfinite(trace_costs.raw_cost_ratio));
	}

	OuterYanDecisionRecord decision;
	decision.selection_mode = selection_mode;
	decision.outer_reordered = outer_reordered;
	decision.baseline_proven_empty = empty_proof.eliminates_all_join_work;
	decision.costs = trace_costs;
	if (trace_costs.available) {
		if (trace_costs.candidate_total < trace_costs.baseline_cost) {
			decision.raw_cost_winner = OuterYanCostWinner::OUTERYAN_CANDIDATE;
		} else if (trace_costs.candidate_total > trace_costs.baseline_cost) {
			decision.raw_cost_winner = OuterYanCostWinner::DUCKDB_BASELINE;
		} else {
			decision.raw_cost_winner = OuterYanCostWinner::EQUAL;
		}
	}

	if (!candidate_cost.has_complete_plan) {
		decision.reason = "OUTERYAN_FAILED";
	} else if (empty_proof.eliminates_all_join_work) {
		decision.reason = "DUCKDB_PROVEN_EMPTY";
	} else if (force_candidate_for_validation) {
		// Diagnostic-only override used by the ON/OFF correctness harness. It
		// deliberately bypasses both grouping equality and the cost gate so the
		// candidate's semi-join plan is executed rather than merely costed.
		decision.selected_plan = OuterYanSelectedPlan::OUTERYAN_CANDIDATE;
		decision.outer_yan_selected = true;
		decision.reason = "FORCE_OUTERYAN_DIAGNOSTIC";
	} else if (!outer_reordered) {
		decision.reason = "DUCKDB_PLAN";
	} else if (!apply_cost_gate) {
		decision.selected_plan = OuterYanSelectedPlan::OUTERYAN_CANDIDATE;
		decision.outer_yan_selected = true;
		decision.reason = "FORCE_OUTERYAN";
	} else if (!trace_costs.available) {
		decision.gate_result = OuterYanGateResult::UNAVAILABLE;
		decision.reason = "COST_UNAVAILABLE";
	} else {
		decision.cost_gate_applied = true;
		if (trace_costs.gate_lhs <= trace_costs.gate_rhs) {
			decision.selected_plan = OuterYanSelectedPlan::OUTERYAN_CANDIDATE;
			decision.outer_yan_selected = true;
			decision.gate_result = OuterYanGateResult::PASS;
			decision.reason = "COST_OUTERYAN_BETTER";
		} else {
			decision.gate_result = OuterYanGateResult::FAIL;
			decision.reason = "COST_DUCKDB_BETTER";
		}
	}
	candidate_tree.stage_stats.outer_reordered = decision.outer_reordered;
	candidate_tree.stage_stats.cost_gate_applied = decision.cost_gate_applied;
	candidate_tree.stage_stats.outer_yan_selected = decision.outer_yan_selected;

	if (OuterYanTrace::Enabled()) {
		OuterYanTrace::Stage("DuckDB baseline join-cost detail",
		                     FormatJoinCostBreakdown("DUCKDB", baseline_breakdown));
		OuterYanTrace::Stage("OuterYan candidate join-cost detail",
		                     FormatJoinCostBreakdown("OUTERYAN_CANDIDATE",
		                                             candidate_cost.candidate_join_breakdown));
		OuterYanTrace::Stage("OuterYan semi-join cost detail", FormatSemijoinCostBreakdown(candidate_cost));
		std::ostringstream costs;
		costs << std::setprecision(17)
		      << "formula_id=" << trace_costs.formula_id << "\n"
		      << "selection_mode=" << decision.selection_mode << "\n"
		      << "apply_cost_gate=" << (apply_cost_gate ? 1 : 0) << "\n"
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
		      << "  round1_pairs=" << trace_costs.round1_pairs << "\n"
		      << "  round1_filters=" << trace_costs.round1_filters << "\n"
		      << "  round2_pairs=" << trace_costs.round2_pairs << "\n"
		      << "  round2_filters=" << trace_costs.round2_filters << "\n"
		      << "candidate_total=" << trace_costs.candidate_total << "\n"
		      << "raw_cost_delta=" << trace_costs.raw_cost_delta << "\n"
		      << "raw_cost_ratio=";
		if (trace_costs.raw_cost_ratio_available) {
			costs << trace_costs.raw_cost_ratio;
		} else {
			costs << "NA";
		}
		costs << "\n"
		      << "cost_ratio_limit=" << std::setprecision(6) << trace_costs.cost_ratio_limit << "\n"
		      << std::setprecision(17)
		      << "baseline_threshold=" << trace_costs.baseline_threshold << "\n"
		      << "inner_output_weight=" << trace_costs.inner_output_weight << "\n"
		      << "unmatched_left_weight=" << trace_costs.unmatched_left_weight << "\n"
		      << "unmatched_right_weight=" << trace_costs.unmatched_right_weight << "\n"
		      << "semijoin_materialize_weight=" << trace_costs.semijoin_materialize_weight << "\n"
		      << "semijoin_filter_build_weight=" << trace_costs.semijoin_filter_build_weight << "\n"
		      << "semijoin_replay_weight=" << trace_costs.semijoin_replay_weight << "\n"
		      << "semijoin_probe_lookup_weight=" << trace_costs.semijoin_probe_lookup_weight << "\n"
		      << "semijoin_probe_emit_weight=" << trace_costs.semijoin_probe_emit_weight << "\n"
		      << "cost_gate_formula=candidate_join_cost + semijoin_cost_ratio * semijoin_raw_cost <= "
		         "cost_ratio_limit * baseline_cost\n"
		      << "cost_gate_values=" << trace_costs.candidate_join_cost << " + " << std::setprecision(6)
		      << trace_costs.semijoin_cost_ratio << std::setprecision(17) << " * " << trace_costs.semijoin_raw_cost
		      << " <= " << std::setprecision(6) << trace_costs.cost_ratio_limit << std::setprecision(17) << " * "
		      << trace_costs.baseline_cost << "\n"
		      << "raw_cost_comparison=" << trace_costs.candidate_total << " vs " << trace_costs.baseline_cost << "\n"
		      << "cost_gate_result=" << trace_costs.gate_lhs << " <= " << trace_costs.gate_rhs << " => ";
		switch (decision.gate_result) {
		case OuterYanGateResult::PASS:
			costs << "PASS";
			break;
		case OuterYanGateResult::FAIL:
			costs << "FAIL";
			break;
		case OuterYanGateResult::SKIPPED:
			costs << "SKIPPED";
			break;
		case OuterYanGateResult::UNAVAILABLE:
			costs << "UNAVAILABLE";
			break;
		}
		costs << "\n";
		OuterYanTrace::Stage("candidate cost comparison", costs.str());
	}
	OuterYanTrace::Decision(decision);

	unique_ptr<LogicalOperator> selected_plan;
	OuterYanTree *selected_tree;
	if (decision.outer_yan_selected) {
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
