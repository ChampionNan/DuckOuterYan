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
	bool pass = false;
	bool stretch_selected = false;
	double cost_ratio_limit = 0.0;
	double baseline_threshold = 0.0;
};

//! Owns the complete two-candidate policy for an OuterYan-applicable query:
//! build the normal DuckDB baseline, build the OuterYan candidate, compare
//! base-relation join groupings, optionally apply the common cost gate, and
//! lower the winner. Queries containing aggregation or DISTINCT bypass this
//! pipeline and continue through DuckDB's normal optimizer unchanged.
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
	//! it to the OuterYan candidate's real-join cost. V7 uses the full modeled
	//! row-work instead of the former 0.50 discount: the 2026-08-18 benchmark
	//! showed that discount admitted candidates whose reducer work dominated the
	//! realized execution time.
	static constexpr double SEMIJOIN_COST_RATIO = 1.0;
	//! GATED-mode selection threshold. A value of 1.0 selects OuterYan only
	//! when its limiting estimated total cost does not exceed DuckDB's baseline
	//! cost. Uncertain table filters are checked under both their estimated and
	//! unfiltered-cardinality scenarios.
	static constexpr double MAX_CANDIDATE_TO_BASELINE_RATIO = 1.0;
	//! Candidates that depend on a material estimated reduction need headroom
	//! for selectivity error and reducer scheduling work. The August 30 corpus
	//! showed that near-tie estimates in this regime consistently regressed.
	static constexpr double LOW_RETENTION_MAX_CANDIDATE_TO_BASELINE_RATIO = 0.90;
	static constexpr double LOW_RETENTION_SEMIJOIN_RETAINED_CARDINALITY_RATIO = 0.90;
	//! A changed candidate may use this relaxed ceiling only when the
	//! confidence predicate succeeds. It is deliberately not a global
	//! multiplier.
	static constexpr double STRETCH_MAX_CANDIDATE_TO_BASELINE_RATIO = 1.20;
	//! Require a material real-join build/probe input reduction before allowing
	//! the stretch tier.
	static constexpr double STRETCH_MAX_JOIN_INPUT_RATIO = 0.30;
	//! The stretch tier is intended for reorder-dominated candidates: reducer
	//! rounds retain nearly all estimated rows, while the changed grouping still
	//! lowers real-join work. Lower-retention candidates must win the strict gate
	//! because their performance depends more heavily on reduction estimates.
	static constexpr double STRETCH_MIN_SEMIJOIN_RETAINED_CARDINALITY_RATIO = 0.95;
	//! A generic-selectivity filter on a tiny relation is too uncertain to drive
	//! a large reorder when the two reducer rounds retain essentially all rows.
	static constexpr double MAX_UNCERTAIN_FILTER_RETAINED_CARDINALITY_RATIO = 0.99;
	static constexpr double MIN_UNCERTAIN_FILTER_CARDINALITY_AMPLIFICATION = 1000.0;

	explicit OuterYanOptimizer(Optimizer &optimizer);

	OuterYanOptimizationResult Optimize(unique_ptr<LogicalOperator> input);

	//! Evaluate the strict 1.0 gate and the confidence-aware stretch gate from
	//! already-computed costs. Hard plan guards (failed candidate, proven empty,
	//! same grouping) remain in Optimize.
	static OuterYanCostGatePolicyResult EvaluateCostGate(const OuterYanDecisionCosts &costs);

private:
	Optimizer &optimizer;
	ClientContext &context;
};

} // namespace duckdb
