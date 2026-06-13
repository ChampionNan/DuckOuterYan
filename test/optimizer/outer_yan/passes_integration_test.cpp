#include "catch.hpp"
#include "test_helpers.hpp"

#include "duckdb.hpp"
#include "duckdb/main/connection.hpp"
#include "duckdb/optimizer/outer_yan/common/ordered_join_tree.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_common.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"
#include "duckdb/planner/logical_operator.hpp"

#include <algorithm>
#include <functional>

using namespace duckdb;

// =============================================================================
// Integration tests for OuterYanPre / OuterYanDP / OuterYanPost — exercised
// through `OuterYanTree::BuildOT`, `BuildOJT`, `OJTToLogicalPlan`. We don't
// attempt to mock OT/OJT directly; the public construction path is the same
// one optimizer.cpp uses and observably covers Phase 0..3 of the plan.
// =============================================================================

namespace {

void SeedPasses(Connection &con) {
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE a(id INTEGER, ax INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE b(id INTEGER, bx INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE c(id INTEGER, cx INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE d(id INTEGER, dx INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO a VALUES (1, 10), (2, 20), (3, 30)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO b VALUES (1, 100), (2, 200)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO c VALUES (1, 1000), (3, 3000)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO d VALUES (2, 20000), (3, 30000)"));
}

//! Build the full IR pipeline up to OJT for `sql`. Returns the populated
//! OuterYanTree so callers can inspect OT, OJT, and applicability.
//!
//! OuterYan passes are disabled before ExtractPlan so the plan is in the same
//! state OuterYanPre would receive it — no SJ operators already inserted.
unique_ptr<OuterYanTree> BuildIRFor(Connection &con, const string &sql) {
	// Disable OuterYan + join_order + column_lifetime so ExtractPlan returns
	// the plan in the same state OuterYanPre would receive it (no SJ ops, no
	// column-lifetime compression projections rewriting table_index values).
	REQUIRE_NO_FAIL(con.Query(
	    "SET disabled_optimizers TO "
	    "'outer_yan_pre,outer_yan_dp,outer_yan_post,join_order,"
	    "column_lifetime,statistics_propagation'"));
	// `resolve_column_bindings=false`: skip ExtractPlan's trailing
	// ColumnBindingResolver so join conditions stay BoundColumnRefs (table_index
	// intact). OuterYanPre runs before that pass in the real pipeline.
	auto plan = con.ExtractPlan(sql, /*resolve_column_bindings=*/false);
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO ''"));
	REQUIRE(plan);
	auto tree = make_uniq<OuterYanTree>();
	if (!tree->CheckApplicability(*plan)) {
		return tree;
	}
	tree->BuildOT(std::move(plan));
	tree->BuildOJT();
	return tree;
}

//! Count OTNode JOIN nodes via a recursive walk.
idx_t CountJoinNodes(const OTNode &node) {
	if (node.kind == OTNode::Kind::RELATION) {
		return 0;
	}
	return 1 + CountJoinNodes(*node.children[0]) + CountJoinNodes(*node.children[1]);
}

idx_t CountRelationNodes(const OTNode &node) {
	if (node.kind == OTNode::Kind::RELATION) {
		return 1;
	}
	return CountRelationNodes(*node.children[0]) + CountRelationNodes(*node.children[1]);
}

// ----------------------------------------------------------------------------
// Result-equivalence helpers (OuterYan disabled vs enabled).
// ----------------------------------------------------------------------------

void SeedRoundtrip(Connection &con) {
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE a(id INTEGER, ax INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE b(id INTEGER, bx INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE c(id INTEGER, cx INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO a VALUES (1, 10), (2, 20), (3, 30), (4, 40)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO b VALUES (1, 100), (2, 200), (3, 300), (5, 500)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO c VALUES (1, 1000), (3, 3000), (4, 4000)"));
}

//! Wider seed for 5..6 relation scale cases.
void SeedWide(Connection &con) {
	SeedRoundtrip(con);
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE d(id INTEGER, dx INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE e(id INTEGER, ex INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE f(id INTEGER, fx INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO d VALUES (2, 20000), (3, 30000), (5, 50000)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO e VALUES (1, 100000), (4, 400000), (5, 500000)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO f VALUES (3, 3000000), (5, 5000000), (6, 6000000)"));
}

//! NULL-rich, duplicate-key seed. Both keys and payloads carry NULLs; k=2 is
//! many-to-many across na/nb (and nd) to exercise multiset (duplicate-row)
//! preservation; several keys are exclusive to one table to force NULL-padding
//! under outer joins. NULL keys never satisfy an equi-join.
void SeedNullable(Connection &con) {
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE na(k INTEGER, v INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE nb(k INTEGER, v INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE nc(k INTEGER, v INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE nd(k INTEGER, v INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO na VALUES (1, 10), (2, 20), (2, 21), "
	                          "(3, NULL), (NULL, 99), (4, 40), (5, 50)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO nb VALUES (2, 200), (2, 201), (3, 300), "
	                          "(5, NULL), (6, 600), (NULL, NULL)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO nc VALUES (1, 1000), (2, 2000), "
	                          "(4, NULL), (6, 6000)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO nd VALUES (2, 20000), (5, 50000), "
	                          "(5, 51000), (7, 70000), (NULL, 90000)"));
}

//! Render a result as a sorted vector of row strings (columns joined by '|',
//! NULL via `Value::ToString`). Sorting makes the comparison independent of
//! storage/row order, so the queries need no `ORDER BY`.
vector<string> CollectSortedRows(MaterializedQueryResult &result) {
	vector<string> rows;
	rows.reserve(result.RowCount());
	for (idx_t r = 0; r < result.RowCount(); r++) {
		string row;
		for (idx_t c = 0; c < result.ColumnCount(); c++) {
			if (c > 0) {
				row += "|";
			}
			row += result.GetValue(c, r).ToString();
		}
		rows.push_back(std::move(row));
	}
	std::sort(rows.begin(), rows.end());
	return rows;
}

//! Full-pipeline equivalence: run `sql` twice and assert identical row
//! multisets.
//!   baseline  — `disabled_optimizers='outer_yan'`: the whole OuterYan path is
//!               skipped, so JOIN_ORDER handles the query (ordinary DuckDB).
//!   optimized — `disabled_optimizers=''`: the full OuterYan pipeline
//!               (Pre → DP → Post → semi-join insertion) runs.
//! Every such query carries an outer join so the applicability gate fires; a
//! pure inner-join query defers to JOIN_ORDER in both configs and would compare
//! equal trivially without exercising OuterYan.
void AssertOuterYanPreservesResults(Connection &con, const string &sql) {
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO 'outer_yan'"));
	auto baseline = con.Query(sql);
	REQUIRE_FALSE(baseline->HasError());

	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO ''"));
	auto optimized = con.Query(sql);
	REQUIRE_FALSE(optimized->HasError());

	REQUIRE(CollectSortedRows(*optimized) == CollectSortedRows(*baseline));
}

} // namespace

// ============================================================================
// OT structural invariants (post-Finalize).
// ============================================================================

TEST_CASE("outer_yan passes: OT::IsValid holds on 3-relation LEFT chain",
          "[outer_yan][passes][ot]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPasses(con);
	auto tree = BuildIRFor(con,
	    "SELECT a.id, b.bx, c.cx FROM a LEFT JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id");
	REQUIRE(tree->HasOT());
	string reason;
	REQUIRE(tree->OT().IsValid(&reason));
	REQUIRE(reason.empty());
}

TEST_CASE("outer_yan passes: OT shape — 3-relation chain has 2 JOINs + 3 RELATIONs",
          "[outer_yan][passes][ot]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPasses(con);
	auto tree = BuildIRFor(con,
	    "SELECT a.id, b.bx, c.cx FROM a LEFT JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id");
	REQUIRE(tree->HasOT());
	REQUIRE(CountJoinNodes(tree->OT().Root()) == 2);
	REQUIRE(CountRelationNodes(tree->OT().Root()) == 3);
}

TEST_CASE("outer_yan passes: OT shape — 4-relation chain has 3 JOINs + 4 RELATIONs",
          "[outer_yan][passes][ot]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPasses(con);
	auto tree = BuildIRFor(con,
	    "SELECT a.id, b.bx, c.cx, d.dx "
	    "FROM a LEFT JOIN b ON a.id = b.id "
	    "       LEFT JOIN c ON a.id = c.id "
	    "       LEFT JOIN d ON a.id = d.id");
	REQUIRE(tree->HasOT());
	REQUIRE(CountJoinNodes(tree->OT().Root()) == 3);
	REQUIRE(CountRelationNodes(tree->OT().Root()) == 4);
}

TEST_CASE("outer_yan passes: OT relation_id uniqueness — each base relation distinct",
          "[outer_yan][passes][ot]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPasses(con);
	auto tree = BuildIRFor(con,
	    "SELECT a.id, b.bx, c.cx FROM a LEFT JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id");
	REQUIRE(tree->HasOT());
	REQUIRE(tree->ot_relations_by_id.size() == 3);
	for (idx_t i = 0; i < tree->ot_relations_by_id.size(); i++) {
		REQUIRE(tree->ot_relations_by_id[i] != nullptr);
		REQUIRE(tree->ot_relations_by_id[i]->kind == OTNode::Kind::RELATION);
		REQUIRE(tree->ot_relations_by_id[i]->relation_id == i);
	}
}

TEST_CASE("outer_yan passes: ot_joins_by_order is sorted ascending by `order`",
          "[outer_yan][passes][ot]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPasses(con);
	auto tree = BuildIRFor(con,
	    "SELECT a.id, b.bx, c.cx, d.dx "
	    "FROM a LEFT JOIN b ON a.id = b.id "
	    "       LEFT JOIN c ON a.id = c.id "
	    "       LEFT JOIN d ON a.id = d.id");
	REQUIRE(tree->HasOT());
	REQUIRE(tree->ot_joins_by_order.size() == 3);
	for (idx_t i = 1; i < tree->ot_joins_by_order.size(); i++) {
		REQUIRE(tree->ot_joins_by_order[i - 1]->order <
		        tree->ot_joins_by_order[i]->order);
	}
}

// ============================================================================
// Simplification — null-rejecting predicate converts LEFT/RIGHT/FULL to INNER.
// Tested through observable behavior: post-Simplify, the OJT's edge `kind`
// (which holds the *simplified* join type) is INNER, while
// `original_kind` retains the source LEFT/RIGHT/FULL.
// ============================================================================

TEST_CASE("outer_yan passes: null-rejecting WHERE simplifies LEFT to INNER",
          "[outer_yan][passes][simplify]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPasses(con);
	// `b.bx > 0` rejects rows where b.bx is NULL, so the LEFT JOIN simplifies
	// to INNER on the (a,b) edge.
	auto tree = BuildIRFor(con,
	    "SELECT a.id, b.bx, c.cx FROM a LEFT JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id WHERE b.bx > 0");
	REQUIRE(tree->HasOJT());
	// At least one OJT edge should have its `kind` lowered to INNER while
	// `original_kind` is still LEFT_OUTER. The edge fields are mirrored from
	// `info->join_kind` / `info->original_join_kind`.
	bool found_simplified = false;
	std::function<void(const OJTNode &)> walk = [&](const OJTNode &node) {
		for (const auto &edge : node.children) {
			if (edge.kind == JoinType::INNER && edge.original_kind != JoinType::INNER) {
				found_simplified = true;
			}
			walk(*edge.child);
		}
	};
	walk(tree->OJT().Root());
	REQUIRE(found_simplified);
}

TEST_CASE("outer_yan passes: no simplification when WHERE preserves NULLs",
          "[outer_yan][passes][simplify]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPasses(con);
	// `b.bx IS NULL OR b.bx > 0` does NOT reject NULL → LEFT stays LEFT.
	auto tree = BuildIRFor(con,
	    "SELECT a.id, b.bx, c.cx FROM a LEFT JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id WHERE b.bx IS NULL OR b.bx > 0");
	REQUIRE(tree->HasOJT());
	// At least one edge retains its outer kind unchanged.
	bool found_outer = false;
	std::function<void(const OJTNode &)> walk = [&](const OJTNode &node) {
		for (const auto &edge : node.children) {
			if (edge.kind != JoinType::INNER && edge.kind == edge.original_kind) {
				found_outer = true;
			}
			walk(*edge.child);
		}
	};
	walk(tree->OJT().Root());
	REQUIRE(found_outer);
}

// ============================================================================
// Semi-join pair recording — bottom-up + top-down passes write into
// `tree.bottom_up_pairs` / `tree.top_down_pairs`. Each pass must produce at
// least one pair for an accepted query, and pairs must be self-consistent.
// ============================================================================

TEST_CASE("outer_yan passes: semi-join pair recording populates both phases",
          "[outer_yan][passes][semi]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPasses(con);
	// We need to drive the FULL `optimizer.cpp` pipeline (not just BuildOJT)
	// because OuterYanPre is what records pairs. Easiest: run a query and
	// confirm via EXPLAIN that SJ_BUILD + SJ_PROBE are inserted (downstream
	// observable signal of recorded pairs).
	REQUIRE_NO_FAIL(con.Query("PRAGMA explain_output='optimized_only'"));
	auto result = con.Query("EXPLAIN SELECT a.id, b.bx, c.cx "
	                        "FROM a LEFT JOIN b ON a.id = b.id "
	                        "LEFT JOIN c ON a.id = c.id");
	REQUIRE_FALSE(result->HasError());
	auto plan_text = result->ToString();
	REQUIRE(plan_text.find("SJ_BUILD") != string::npos);
	REQUIRE(plan_text.find("SJ_PROBE") != string::npos);
}

// ============================================================================
// OJT structure — verify OJT has a single root and the relation count matches.
// ============================================================================

TEST_CASE("outer_yan passes: OJT has the same relation count as OT",
          "[outer_yan][passes][ojt]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPasses(con);
	auto tree = BuildIRFor(con,
	    "SELECT a.id, b.bx, c.cx FROM a LEFT JOIN b ON a.id = b.id "
	    "LEFT JOIN c ON a.id = c.id");
	REQUIRE(tree->HasOJT());

	// Walk OJT and count nodes.
	idx_t ojt_nodes = 0;
	std::function<void(const OJTNode &)> walk = [&](const OJTNode &node) {
		ojt_nodes++;
		for (const auto &edge : node.children) {
			walk(*edge.child);
		}
	};
	walk(tree->OJT().Root());
	REQUIRE(ojt_nodes == 3);
}

TEST_CASE("outer_yan passes: OJT root has subtree containing all relations",
          "[outer_yan][passes][ojt]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPasses(con);
	auto tree = BuildIRFor(con,
	    "SELECT a.id, b.bx, c.cx, d.dx "
	    "FROM a LEFT JOIN b ON a.id = b.id "
	    "       LEFT JOIN c ON a.id = c.id "
	    "       LEFT JOIN d ON a.id = d.id");
	REQUIRE(tree->HasOJT());

	// Collect every relation_id reachable from OJT root.
	unordered_set<idx_t> reachable;
	std::function<void(const OJTNode &)> walk = [&](const OJTNode &node) {
		reachable.insert(node.relation_id);
		for (const auto &edge : node.children) {
			walk(*edge.child);
		}
	};
	walk(tree->OJT().Root());
	REQUIRE(reachable.size() == 4);
}

// ============================================================================
// Result equivalence — OuterYan disabled (ordinary DuckDB / JOIN_ORDER) vs
// enabled (Pre → DP → Post). The full pipeline must reproduce the baseline row
// multiset. Join conditions are binary equi-joins; residual WHERE filters
// reference a single relation on the preserved side; every query carries an
// outer join so the applicability gate fires.
// ============================================================================

TEST_CASE("outer_yan passes: equivalence — 2-relation LEFT join",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	// NULL/non-matching left rows survive NULL-padded; k=2 is 2x2 many-to-many.
	AssertOuterYanPreservesResults(con, "SELECT na.k, na.v, nb.v "
	                                     "FROM na LEFT JOIN nb ON na.k = nb.k");
}

TEST_CASE("outer_yan passes: equivalence — 2-relation RIGHT join",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	AssertOuterYanPreservesResults(con, "SELECT na.v, nb.k, nb.v "
	                                     "FROM na RIGHT JOIN nb ON na.k = nb.k");
}

TEST_CASE("outer_yan passes: equivalence — 2-relation FULL OUTER join",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	// Exclusive keys (1,4 vs 6) and NULL keys on both sides surface NULL-padded.
	AssertOuterYanPreservesResults(con, "SELECT na.k, na.v, nb.k, nb.v "
	                                     "FROM na FULL OUTER JOIN nb ON na.k = nb.k");
}

TEST_CASE("outer_yan passes: equivalence — 3-relation LEFT chain",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	AssertOuterYanPreservesResults(con, "SELECT na.k, nb.v, nc.v "
	                                     "FROM na "
	                                     "LEFT JOIN nb ON na.k = nb.k "
	                                     "LEFT JOIN nc ON na.k = nc.k");
}

TEST_CASE("outer_yan passes: equivalence — RIGHT-flip mirror + LEFT tail",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	// `nb RIGHT JOIN na` mirrors `na LEFT JOIN nb`; OJT parent-orientation may
	// flip RIGHT↔LEFT — a flip that loses NULL-padded rows would mismatch.
	AssertOuterYanPreservesResults(con, "SELECT na.k, nb.v, nc.v "
	                                     "FROM nb "
	                                     "RIGHT JOIN na ON na.k = nb.k "
	                                     "LEFT JOIN nc ON na.k = nc.k");
}

TEST_CASE("outer_yan passes: equivalence — FULL OUTER head + LEFT tail",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	AssertOuterYanPreservesResults(con, "SELECT na.k, nb.v, nc.v "
	                                     "FROM na "
	                                     "FULL OUTER JOIN nb ON na.k = nb.k "
	                                     "LEFT JOIN nc ON na.k = nc.k");
}

TEST_CASE("outer_yan passes: equivalence — mixed INNER/LEFT/FULL chain",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	// Three different join kinds in one skeleton, all keyed on na.k.
	AssertOuterYanPreservesResults(con, "SELECT na.v, nb.v, nc.v, nd.v "
	                                     "FROM na "
	                                     "INNER JOIN nb ON na.k = nb.k "
	                                     "LEFT JOIN nc ON na.k = nc.k "
	                                     "FULL OUTER JOIN nd ON na.k = nd.k");
}

TEST_CASE("outer_yan passes: equivalence — 4-relation LEFT chain",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	AssertOuterYanPreservesResults(con, "SELECT na.k, nb.v, nc.v, nd.v "
	                                     "FROM na "
	                                     "LEFT JOIN nb ON na.k = nb.k "
	                                     "LEFT JOIN nc ON na.k = nc.k "
	                                     "LEFT JOIN nd ON na.k = nd.k");
}

TEST_CASE("outer_yan passes: equivalence — LEFT join with preserved-side residual filter",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	// `na.v > 15` is a single-relation residual on the preserved side; pushing
	// it onto leaf na is semantics-preserving (NULL `na.v` is filtered out).
	AssertOuterYanPreservesResults(con, "SELECT na.k, na.v, nb.v "
	                                     "FROM na LEFT JOIN nb ON na.k = nb.k "
	                                     "WHERE na.v > 15");
}

TEST_CASE("outer_yan passes: equivalence — compound equi-join condition on a LEFT edge",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	// Compound key on the (na, nb) edge; each side of every condition references
	// a single relation, so both stay binary and swappable.
	AssertOuterYanPreservesResults(con, "SELECT na.k, na.v, nb.v, nc.v "
	                                     "FROM na "
	                                     "LEFT JOIN nb ON na.k = nb.k AND na.v = nb.v - 180 "
	                                     "LEFT JOIN nc ON na.k = nc.k");
}

TEST_CASE("outer_yan passes: equivalence — bushy tree with an outer join",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	// Parenthesised joins build a bushy skeleton ((na,nb),(nc,nd)); the outer
	// join on the left arm activates OuterYan.
	AssertOuterYanPreservesResults(con, "SELECT na.v, nb.v, nc.v, nd.v "
	                                     "FROM (na LEFT JOIN nb ON na.k = nb.k) "
	                                     "INNER JOIN (nc INNER JOIN nd ON nc.k = nd.k) "
	                                     "ON na.k = nc.k");
}

TEST_CASE("outer_yan passes: equivalence — projection prunes to a single column",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	// Output is a single column from the null-supplying side; the rebuilt
	// projection cap must reproduce exactly this schema.
	AssertOuterYanPreservesResults(con, "SELECT nb.v "
	                                     "FROM na LEFT JOIN nb ON na.k = nb.k");
}

TEST_CASE("outer_yan passes: equivalence — 5-relation LEFT chain stresses DP enumeration",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedWide(con);
	AssertOuterYanPreservesResults(con, "SELECT a.id, b.bx, c.cx, d.dx, e.ex "
	                                     "FROM a "
	                                     "LEFT JOIN b ON a.id = b.id "
	                                     "LEFT JOIN c ON a.id = c.id "
	                                     "LEFT JOIN d ON a.id = d.id "
	                                     "LEFT JOIN e ON a.id = e.id");
}

TEST_CASE("outer_yan passes: equivalence — 6-relation LEFT star",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedWide(con);
	AssertOuterYanPreservesResults(con, "SELECT a.id, b.bx, c.cx, d.dx, e.ex, f.fx "
	                                     "FROM a "
	                                     "LEFT JOIN b ON a.id = b.id "
	                                     "LEFT JOIN c ON a.id = c.id "
	                                     "LEFT JOIN d ON a.id = d.id "
	                                     "LEFT JOIN e ON a.id = e.id "
	                                     "LEFT JOIN f ON a.id = f.id");
}

// `LogicalPlanToOT` throws NotImplementedException when a residual filter's
// `BoundColumnRef`s all resolve to a `table_index` introduced by a
// `LogicalProjection` above the join tree (no registered OT base relation).
// This is the one isolated-conversion check: the gate hides this in production
// (the query is a pure inner join), so result-equivalence can't surface it.
// Hidden by `[.]`; run with explicit tag.
TEST_CASE("outer_yan passes: residual filter via projection (UNSUPPORTED)",
          "[outer_yan][passes][equivalence][.]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedRoundtrip(con);
	const string sql = "SELECT t.id, t.b_total "
	                   "FROM (SELECT a.id AS id, b.bx AS b_total "
	                   "      FROM a INNER JOIN b ON a.id = b.id) AS t "
	                   "WHERE t.b_total > 150";
	auto plan = con.ExtractPlan(sql, /*resolve_column_bindings=*/false);
	REQUIRE(plan);
	OuterYanTree tree;
	REQUIRE_THROWS_AS(LogicalPlanToOT(std::move(plan), tree), NotImplementedException);
}

// ============================================================================
// Resimplification — when the chosen ordering allows it, INNER edges that
// came from OUTER (recorded in `original_kind`) are reverted back to OUTER.
// Observable through correctness on outer-join queries; structural assertion
// hard without internal access. Tested via end-to-end correctness above.
// ============================================================================

TEST_CASE("outer_yan passes: applicability rejection short-circuits — no OT built",
          "[outer_yan][passes][applicability]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPasses(con);
	auto tree = BuildIRFor(con, "SELECT a.id, b.bx FROM a JOIN b ON a.id = b.id");
	REQUIRE_FALSE(tree->Applicability().applicable);
	REQUIRE_FALSE(tree->HasOT());
	REQUIRE_FALSE(tree->HasOJT());
}
