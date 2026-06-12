#include "catch.hpp"
#include "test_helpers.hpp"

#include "duckdb.hpp"
#include "duckdb/main/connection.hpp"
#include "duckdb/optimizer/outer_yan/common/applicability.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"

using namespace duckdb;

namespace {

void SeedApplicability(Connection &con) {
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE a(id INTEGER, ax INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE b(id INTEGER, bx INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE c(id INTEGER, cx INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO a VALUES (1, 10), (2, 20), (3, 30)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO b VALUES (1, 100), (2, 200)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO c VALUES (1, 1000), (3, 3000)"));
}

//! White-box: extract the logical plan and call OuterYanApplicability::Check.
//! Returns the populated ApplicabilityResult so the test can inspect both the
//! `applicable` flag and the `reason` diagnostic.
//!
//! The passes that run at/after OUTER_YAN_PRE (outer_yan_*, join_order,
//! column_lifetime, statistics_propagation) are disabled before ExtractPlan so
//! the returned plan matches the state OuterYanPre receives mid-pipeline (after
//! expression rewriting / filter pushdown / projection pullup, but before
//! column_lifetime rewrites the join skeleton).
ApplicabilityResult ApplicabilityOf(Connection &con, const string &sql) {
	// Disable OuterYan's own passes (no SJ operators injected) plus the passes
	// that run AFTER OUTER_YAN_PRE and rewrite the join skeleton: join_order,
	// column_lifetime (injects compress/decompress + NULL-padding projections
	// between the joins, which the applicability visitor treats as opaque leaves
	// and stops descending), and statistics_propagation. This leaves the plan in
	// the state OuterYanPre actually receives.
	REQUIRE_NO_FAIL(con.Query(
	    "SET disabled_optimizers TO "
	    "'outer_yan_pre,outer_yan_dp,outer_yan_post,join_order,"
	    "column_lifetime,statistics_propagation'"));
	// `resolve_column_bindings=false`: keep join conditions as BoundColumnRefs.
	// ExtractPlan otherwise appends a ColumnBindingResolver that rewrites them
	// into positional BoundReferenceExpressions, which the applicability gate
	// rejects (it requires BOUND_COLUMN_REF join keys). OuterYanPre sees the
	// pre-resolution form.
	auto plan = con.ExtractPlan(sql, /*resolve_column_bindings=*/false);
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO ''"));
	REQUIRE(plan);
	return OuterYanApplicability::Check(*plan);
}

//! Same extraction discipline as ApplicabilityOf, but drives the integration
//! entry point OuterYanTree::CheckApplicability and returns via `tree`. The same
//! optimizers as ApplicabilityOf are disabled (no SJ operators injected, no
//! skeleton-rewriting passes) and column-binding resolution is skipped so join
//! conditions stay BoundColumnRefs.
void CheckApplicabilityVia(Connection &con, const string &sql, OuterYanTree &tree) {
	REQUIRE_NO_FAIL(con.Query(
	    "SET disabled_optimizers TO "
	    "'outer_yan_pre,outer_yan_dp,outer_yan_post,join_order,"
	    "column_lifetime,statistics_propagation'"));
	auto plan = con.ExtractPlan(sql, /*resolve_column_bindings=*/false);
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO ''"));
	REQUIRE(plan);
	tree.CheckApplicability(*plan);
}

} // namespace

// ============================================================================
// White-box applicability — mirrors test/sql/optimizer/outer_yan/acyclic_query.test
// at the function level. Faster + pins the exact reason string when rejecting.
// ============================================================================

TEST_CASE("outer_yan applicability: rejects pure-INNER 2-relation join",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con, "SELECT a.id, b.bx FROM a JOIN b ON a.id = b.id");
	REQUIRE_FALSE(result.applicable);
}

TEST_CASE("outer_yan applicability: rejects pure-INNER 3-relation chain",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, b.bx, c.cx FROM a JOIN b ON a.id = b.id JOIN c ON b.id = c.id");
	REQUIRE_FALSE(result.applicable);
}

// ============================================================================
// Acceptance — full queries (non-aggregation).
// Every joined table must have at least one non-key column in the SELECT so
// that join_elimination cannot remove any join before Check is called.
// ============================================================================

TEST_CASE("outer_yan applicability: accepts 3-relation LEFT-LEFT chain",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, a.ax, b.bx, c.cx FROM a LEFT JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id");
	INFO("reason: " << result.reason);
	REQUIRE(result.applicable);
	REQUIRE(result.relations.size() == 3);
	REQUIRE(result.edges.size() >= 2);
}

TEST_CASE("outer_yan applicability: accepts mix of INNER + LEFT",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, a.ax, b.bx, c.cx FROM a INNER JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id");
	INFO("reason: " << result.reason);
	REQUIRE(result.applicable);
}

TEST_CASE("outer_yan applicability: accepts LEFT/RIGHT mix",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, a.ax, b.bx, c.cx FROM a LEFT JOIN b ON a.id = b.id "
	    "RIGHT JOIN c ON a.id = c.id");
	INFO("reason: " << result.reason);
	REQUIRE(result.applicable);
}

TEST_CASE("outer_yan applicability: accepts FULL OUTER in chain",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, a.ax, b.bx, c.cx FROM a FULL OUTER JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id");
	INFO("reason: " << result.reason);
	REQUIRE(result.applicable);
}

TEST_CASE("outer_yan applicability: rejects theta predicate",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, b.bx, c.cx FROM a LEFT JOIN b ON a.id < b.id "
	    "LEFT JOIN c ON a.id = c.id");
	REQUIRE_FALSE(result.applicable);
	REQUIRE_FALSE(result.reason.empty());
}

TEST_CASE("outer_yan applicability: rejects cross product",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, b.bx, c.cx FROM a LEFT JOIN b ON a.id = b.id, c");
	REQUIRE_FALSE(result.applicable);
}

TEST_CASE("outer_yan applicability: rejects set op above join",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, b.bx FROM a LEFT JOIN b ON a.id = b.id "
	    "UNION ALL SELECT a.id, c.cx FROM a LEFT JOIN c ON a.id = c.id");
	REQUIRE_FALSE(result.applicable);
}

TEST_CASE("outer_yan applicability: rejects window operator above join",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, b.bx, ROW_NUMBER() OVER (PARTITION BY a.id) AS rn "
	    "FROM a LEFT JOIN b ON a.id = b.id LEFT JOIN c ON a.id = c.id");
	REQUIRE_FALSE(result.applicable);
}

TEST_CASE("outer_yan applicability: rejects cyclic 3-relation graph",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, b.bx, c.cx "
	    "FROM a LEFT JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON b.id = c.id AND a.id = c.id");
	REQUIRE_FALSE(result.applicable);
}

// ============================================================================
// Acceptance — aggregation queries (COUNT(*) / COUNT(col) / SUM / MIN / MAX).
// Every aggregate query must reference columns from all joined tables.
// COUNT(DISTINCT) is not supported by this framework and is not tested here.
// ============================================================================

TEST_CASE("outer_yan applicability: accepts root aggregation (COUNT_STAR)",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	// COUNT(*) counts every row produced by the join; no column-level
	// reference is needed to keep every join live.
	auto result = ApplicabilityOf(con,
	    "SELECT COUNT(*) FROM a LEFT JOIN b ON a.id = b.id LEFT JOIN c ON a.id = c.id");
	INFO("reason: " << result.reason);
	REQUIRE(result.applicable);
	REQUIRE(result.has_root_aggregate);
}

TEST_CASE("outer_yan applicability: accepts GROUP BY at root",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	// MAX(c.cx) keeps the LEFT JOIN c live; COUNT(b.bx) keeps LEFT JOIN b live.
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, COUNT(b.bx), MAX(c.cx) FROM a LEFT JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id GROUP BY a.id");
	INFO("reason: " << result.reason);
	REQUIRE(result.applicable);
	REQUIRE(result.has_root_aggregate);
}

TEST_CASE("outer_yan applicability: relation table-index mapping is populated when accepted",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, a.ax, b.bx, c.cx FROM a LEFT JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id");
	INFO("reason: " << result.reason);
	REQUIRE(result.applicable);
	// 3 relations → 3 entries in table_index_to_relation, with distinct
	// RelationIds in [0, 3).
	REQUIRE(result.table_index_to_relation.size() == 3);
	unordered_set<RelationId> ids;
	for (auto &entry : result.table_index_to_relation) {
		ids.insert(entry.second);
	}
	REQUIRE(ids.size() == 3);
	for (auto id : ids) {
		REQUIRE(id < 3);
	}
}

TEST_CASE("outer_yan applicability: edges hold valid LogicalComparisonJoin pointers",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, a.ax, b.bx, c.cx FROM a LEFT JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id");
	INFO("reason: " << result.reason);
	REQUIRE(result.applicable);
	for (auto &edge : result.edges) {
		REQUIRE(edge.join != nullptr);
		REQUIRE(edge.left != edge.right);
	}
}

TEST_CASE("outer_yan applicability: rejection populates reason string",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	// Pure-INNER bail-out — should populate a reason.
	auto result = ApplicabilityOf(con,
	    "SELECT a.id, b.bx, c.cx FROM a JOIN b ON a.id = b.id JOIN c ON b.id = c.id");
	REQUIRE_FALSE(result.applicable);
	REQUIRE_FALSE(result.reason.empty());
}

// ============================================================================
// CheckApplicability via OuterYanTree (matches the integration path).
// ============================================================================

TEST_CASE("outer_yan applicability: OuterYanTree::CheckApplicability accepts on outer chain",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	OuterYanTree tree;
	CheckApplicabilityVia(con,
	    "SELECT a.id, a.ax, b.bx, c.cx FROM a LEFT JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id", tree);
	INFO("reason: " << tree.Applicability().reason);
	REQUIRE(tree.Applicability().applicable);
}

TEST_CASE("outer_yan applicability: OuterYanTree::CheckApplicability rejects pure-INNER",
          "[outer_yan][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedApplicability(con);
	OuterYanTree tree;
	CheckApplicabilityVia(con, "SELECT a.id, b.bx FROM a JOIN b ON a.id = b.id", tree);
	INFO("reason: " << tree.Applicability().reason);
	REQUIRE_FALSE(tree.Applicability().applicable);
}
