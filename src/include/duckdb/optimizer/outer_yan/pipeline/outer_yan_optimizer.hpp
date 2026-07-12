//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/pipeline/outer_yan_optimizer.hpp
//
//===----------------------------------------------------------------------===//

#pragma once

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
//! base-relation join groupings, optionally apply the common cost gate, lower
//! the winner, and run aggregate pushdown with winner-local metadata.
class OuterYanOptimizer {
public:
	//! Final candidate-cost judgment. This is deliberately a class-local
	//! source-level knob rather than a session/environment setting, so one
	//! build has one unambiguous experiment policy.
	static constexpr bool APPLY_COST_GATE = true;
	//! Scale the raw row-work estimate for both semi-join rounds before adding
	//! it to the OuterYan candidate's real-join cost.
	static constexpr double SEMIJOIN_COST_RATIO = 0.05;
	//! Permit the weighted candidate cost to be up to 10%
	//! more than DuckDB's baseline estimate before falling back.
	static constexpr double MAX_CANDIDATE_TO_BASELINE_RATIO = 1.2;

	explicit OuterYanOptimizer(Optimizer &optimizer);

	OuterYanOptimizationResult Optimize(unique_ptr<LogicalOperator> input);

private:
	Optimizer &optimizer;
	ClientContext &context;
};

} // namespace duckdb
