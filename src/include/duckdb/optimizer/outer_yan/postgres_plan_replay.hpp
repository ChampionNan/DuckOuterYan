//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/postgres_plan_replay.hpp
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/optional.hpp"
#include "duckdb/common/string.hpp"
#include "duckdb/common/unordered_map.hpp"
#include "duckdb/common/unique_ptr.hpp"
#include "duckdb/planner/logical_operator.hpp"

namespace duckdb {

class ClientContext;

//! Result of importing a duckyan.pg_join_tree.v1 artifact. The expected
//! semantic signature is retained by Optimizer until all later logical
//! optimizers have run, then passed to VerifyFinalPlan.
struct PostgresPlanReplayResult {
	unique_ptr<LogicalOperator> plan;
	string artifact_path;
	string query_sha256;
	string artifact_raw_signature;
	string expected_semantic_signature;
	//! Stable identity assigned from the original bound query. This must survive
	//! pruning and later optimizer passes so repeated scans are never renumbered.
	unordered_map<idx_t, idx_t> occurrence_by_table_index;
};

//! Imports only PostgreSQL's typed logical join tree. Predicates, filters,
//! projections, and scan bindings always come from DuckDB's bound plan.
class PostgresPlanReplay {
public:
	explicit PostgresPlanReplay(ClientContext &context);

	//! Returns the absolute artifact path from SET VARIABLE pgplan, or from the
	//! legacy outer_yan_pg_replay_plan alias. Returns empty when PGPlan is
	//! disabled. A present but NULL/empty/non-string/relative value is an error.
	static optional<string> ConfiguredPlanPath(ClientContext &context);

	//! Apply the configured artifact to input. The caller should invoke this
	//! after filter pushdown/projection pullup and before OuterYan, outer-join
	//! simplification, and native join ordering.
	PostgresPlanReplayResult Apply(unique_ptr<LogicalOperator> input);

	//! Side-normalized semantic signature of a logical plan. INNER and FULL
	//! children are unordered; LEFT/RIGHT are represented as preserved/null
	//! operands. This admits only legal physical child swaps with LEFT/RIGHT
	//! inversion.
	static string SemanticSignature(const LogicalOperator &plan);

	//! Verify that later optimizers retained the imported grouping and preserved
	//! sides. Throws rather than falling back on any difference and emits the
	//! final machine-readable [PGPLAN] diagnostic on success.
	static void VerifyFinalPlan(const LogicalOperator &plan, const string &expected_semantic_signature,
	                            const string &artifact_path);
	static void VerifyFinalPlan(const LogicalOperator &plan, const string &expected_semantic_signature,
	                            const string &artifact_path,
	                            const unordered_map<idx_t, idx_t> &occurrence_by_table_index);

	static constexpr const char *VARIABLE_NAME = "pgplan";
	static constexpr const char *LEGACY_VARIABLE_NAME = "outer_yan_pg_replay_plan";

private:
	ClientContext &context;
};

} // namespace duckdb
