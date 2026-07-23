//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/pipeline/outer_yan_optimizer.hpp
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/types.hpp"
#include "duckdb/common/unique_ptr.hpp"
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
	static constexpr SelectionMode SELECTION_MODE = SelectionMode::FORCE_OUTERYAN;
	static constexpr bool APPLY_COST_GATE = SELECTION_MODE == SelectionMode::GATED;
	//! Scale the raw row-work estimate for both semi-join rounds before adding
	//! it to the OuterYan candidate's real-join cost.
	static constexpr double SEMIJOIN_COST_RATIO = 0.35;
	//! GATED-mode selection tolerance. A value of 1.10 admits an OuterYan
	//! candidate whose estimated total cost is within 10% of DuckDB's baseline.
	//! This is an explicit preference bias, not a physical-cost calibration.
	static constexpr double MAX_CANDIDATE_TO_BASELINE_RATIO = 1.10;

	explicit OuterYanOptimizer(Optimizer &optimizer);

	OuterYanOptimizationResult Optimize(unique_ptr<LogicalOperator> input);

private:
	Optimizer &optimizer;
	ClientContext &context;
};

} // namespace duckdb
