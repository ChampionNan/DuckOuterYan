//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/pipeline/outer_yan_optimizer.hpp
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/types.hpp"
#include "duckdb/common/unique_ptr.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_trace.hpp"
#include "duckdb/planner/logical_operator.hpp"

namespace duckdb {

class ClientContext;
class Optimizer;

//! Result of the self-contained OuterYan candidate selection. When
//! `outer_yan_applied` is false the caller must continue through DuckDB's
//! normal outer-join simplification and join-order passes.
struct OuterYanOptimizationResult {
	unique_ptr<LogicalOperator> plan;
	bool outer_yan_applied = false;
};

//! Pure result of the numeric candidate gate. Keeping this policy independent
//! of plan construction makes its strict/stretch boundaries directly testable.
struct OuterYanCostGatePolicyResult {
	bool available = false;
	bool stretch_eligible = false;
	bool low_selectivity_eligible = false;
	bool pass = false;
	bool stretch_selected = false;
	bool low_selectivity_selected = false;
	double cost_ratio_limit = 0.0;
	double low_selectivity_cost_ratio_limit = 0.0;
	double baseline_threshold = 0.0;
};

//! Owns the complete two-candidate policy for an OuterYan-applicable query:
//! build the normal DuckDB baseline, build the OuterYan candidate, compare
//! base-relation join groupings, optionally apply the common cost gate, and
//! lower the winner. Supported root aggregation and DISTINCT queries use the
//! same candidate construction with a non-relaxed cost gate; only an
//! accepted OuterYan candidate may receive OuterYan aggregate pushdown.
class OuterYanOptimizer {
public:
	//! Final candidate-selection policy. This is deliberately a class-local
	//! source-level knob rather than a session/environment setting, so one
	//! build has one unambiguous experiment policy. Change SELECTION_MODE and
	//! rebuild to switch experiment modes.
	enum class SelectionMode : uint8_t { GATED, FORCE_OUTERYAN };
	static constexpr SelectionMode SELECTION_MODE = SelectionMode::GATED;
	static constexpr bool APPLY_COST_GATE = SELECTION_MODE == SelectionMode::GATED;
	//! Scale the raw row-work estimate for both semi-join rounds before adding
	//! it to the OuterYan candidate's real-join cost. The paper-example
	//! experiment uses 0.20 so the DP-selected order can pass the normal gate.
	//! This is an experimental relative weight, not a calibrated runtime model;
	//! restore 1.0 for the prior conservative corpus policy.
	static constexpr double SEMIJOIN_COST_RATIO = 0.20;
	//! GATED-mode selection threshold. All strict tiers currently allow up to
	//! 20% higher limiting estimated total cost than DuckDB's baseline. This is
	//! an estimated-work allowance, not a bound on runtime slowdown. Uncertain
	//! table filters still use both estimated and unfiltered-cardinality scenarios.
	static constexpr double MAX_CANDIDATE_TO_BASELINE_RATIO = 1.20;
	//! Root aggregation/DISTINCT uses the same ceiling without relaxed tiers.
	//! Aggregate-pushdown benefit is deliberately not credited by the gate.
	static constexpr double AGGREGATE_MAX_CANDIDATE_TO_BASELINE_RATIO = 1.20;
	//! Keep a separate knob for reduction-dependent candidates so experiments
	//! can require extra headroom without tightening other candidates' gate.
	static constexpr double LOW_RETENTION_MAX_CANDIDATE_TO_BASELINE_RATIO = 1.20;
	static constexpr double LOW_RETENTION_SEMIJOIN_RETAINED_CARDINALITY_RATIO = 0.90;
	//! A changed candidate may use this ceiling when the confidence predicate
	//! succeeds. With all strict limits at 1.20, the relaxed tiers add no further
	//! allowance; their eligibility remains available for diagnostics and tuning.
	static constexpr double STRETCH_MAX_CANDIDATE_TO_BASELINE_RATIO = 1.20;
	//! Require a material real-join build/probe input reduction before allowing
	//! the stretch tier.
	static constexpr double STRETCH_MAX_JOIN_INPUT_RATIO = 0.30;
	//! The stretch tier is intended for reorder-dominated candidates: reducer
	//! rounds retain nearly all estimated rows, while the changed grouping still
	//! lowers real-join work. Lower-retention candidates must win the strict gate
	//! because their performance depends more heavily on reduction estimates.
	static constexpr double STRETCH_MIN_SEMIJOIN_RETAINED_CARDINALITY_RATIO = 0.95;
	//! A stats-backed unary filter at or below this selectivity may use a
	//! continuous relaxed tier. The limit starts at the ordinary strict limit
	//! at 0.35 and approaches 1.20 as selectivity approaches zero.
	static constexpr double LOW_UNARY_FILTER_SELECTIVITY_THRESHOLD = 0.35;
	static constexpr double LOW_SELECTIVITY_MAX_CANDIDATE_TO_BASELINE_RATIO = 1.20;
	//! Still require the reordered real joins to reduce estimated input work;
	//! this tier is broader than the 0.30 reorder-only stretch tier because a
	//! selective unary predicate can make reducer propagation itself valuable.
	static constexpr double LOW_SELECTIVITY_MAX_JOIN_INPUT_RATIO = 0.75;
	//! A generic-selectivity filter on a tiny relation is too uncertain to drive
	//! a large reorder when the two reducer rounds retain essentially all rows.
	static constexpr double MAX_UNCERTAIN_FILTER_RETAINED_CARDINALITY_RATIO = 0.99;
	static constexpr double MIN_UNCERTAIN_FILTER_CARDINALITY_AMPLIFICATION = 1000.0;

	explicit OuterYanOptimizer(Optimizer &optimizer);

	OuterYanOptimizationResult Optimize(unique_ptr<LogicalOperator> input);

	//! Evaluate the strict gate plus the confidence-aware stretch and
	//! stats-backed low-selectivity tiers from already-computed costs. Hard plan
	//! guards (failed candidate, proven empty, same grouping) remain in Optimize.
	static OuterYanCostGatePolicyResult EvaluateCostGate(const OuterYanDecisionCosts &costs,
	                                                   bool aggregate_query = false);

private:
	Optimizer &optimizer;
	ClientContext &context;
};

} // namespace duckdb
