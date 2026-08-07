#include "catch.hpp"
#include "test_helpers.hpp"

#include "duckdb.hpp"
#include "duckdb/catalog/catalog_entry/table_catalog_entry.hpp"
#include "duckdb/main/client_context.hpp"
#include "duckdb/main/connection.hpp"
#include "duckdb/optimizer/outer_yan/common/ordered_join_tree.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_common.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_dp.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_post.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_pre.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/simplification.hpp"
#include "duckdb/planner/logical_operator.hpp"
#include "duckdb/planner/operator/logical_get.hpp"

#include <algorithm>
#include <cstdlib>
#include <cstdio>
#include <functional>

using namespace duckdb;

// =============================================================================
// Integration tests for OuterYanPre / OuterYanDP / OuterYanPost — exercised
// through `OuterYanTree::BuildOT`, `BuildOJT`, `OJTToLogicalPlan`. We don't
// attempt to mock OT/OJT directly; the public construction path is the same
// one optimizer.cpp uses and observably covers Phase 0..3 of the plan.
// =============================================================================

namespace {

class ScopedOuterYanCandidateForce {
public:
	ScopedOuterYanCandidateForce() {
		const auto current_value = std::getenv("DUCKDB_OY_FORCE_CANDIDATE");
		if (current_value) {
			had_previous_value = true;
			previous_value = current_value;
		}
#ifdef _WIN32
		if (_putenv_s("DUCKDB_OY_FORCE_CANDIDATE", "1") != 0) {
#else
		if (setenv("DUCKDB_OY_FORCE_CANDIDATE", "1", 1) != 0) {
#endif
			throw InternalException("Failed to set DUCKDB_OY_FORCE_CANDIDATE for test");
		}
	}

	~ScopedOuterYanCandidateForce() {
#ifdef _WIN32
		_putenv_s("DUCKDB_OY_FORCE_CANDIDATE", had_previous_value ? previous_value.c_str() : "");
#else
		if (had_previous_value) {
			setenv("DUCKDB_OY_FORCE_CANDIDATE", previous_value.c_str(), 1);
		} else {
			unsetenv("DUCKDB_OY_FORCE_CANDIDATE");
		}
#endif
	}

	ScopedOuterYanCandidateForce(const ScopedOuterYanCandidateForce &) = delete;
	ScopedOuterYanCandidateForce &operator=(const ScopedOuterYanCandidateForce &) = delete;

private:
	bool had_previous_value = false;
	string previous_value;
};

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
	// Also disable filter_pushdown + outer_join_simplification: both natively
	// rewrite a null-rejected LEFT join to INNER before OuterYan runs, which
	// would hide OuterYan's own Simplify pass (the (a,b) edge would already read
	// INNER with no record it was ever LEFT). Keeping them off lets the LEFT join
	// and its residual filter reach BuildOT intact, so Simplify below is what
	// lowers the kind while preserving `original_kind`.
	REQUIRE_NO_FAIL(con.Query(
	    "SET disabled_optimizers TO "
	    "'outer_yan_pre,outer_yan_dp,outer_yan_post,join_order,"
	    "column_lifetime,statistics_propagation,filter_pushdown,"
	    "outer_join_simplification'"));
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
	// Mirror production OuterYanPre order (BuildOT -> Simplify -> BuildOJT):
	// Simplify lowers outer joins to INNER where a recorded null-rejecting
	// filter permits, mutating only `OTJoin::join_kind` and leaving
	// `original_join_kind` so BuildOJT can surface the kind/original_kind split.
	Simplification().Apply(*tree);
	tree->BuildOJT();
	return tree;
}

//! Drive the COMPLETE OuterYan pipeline (Pre → DP → Post) on `sql`, exactly as
//! optimizer.cpp does, and keep the `OuterYanTree` afterwards so a caller can
//! read `tree->stage_stats` — every stage records what it changed there before
//! Post consumes the OJT. The lowered plan is discarded; we want the per-stage
//! transformation counters, not the plan. A non-applicable query returns a tree
//! with `HasOT() == false`.
unique_ptr<OuterYanTree> BuildFullIRFor(Connection &con, const string &sql) {
	REQUIRE_NO_FAIL(con.Query(
	    "SET disabled_optimizers TO "
	    "'outer_yan_pre,outer_yan_dp,outer_yan_post,join_order,"
	    "column_lifetime,statistics_propagation,filter_pushdown,"
	    "outer_join_simplification'"));
	auto plan = con.ExtractPlan(sql, /*resolve_column_bindings=*/false);
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO ''"));
	REQUIRE(plan);
	auto tree = make_uniq<OuterYanTree>();
	if (!tree->CheckApplicability(*plan)) {
		return tree;
	}
	auto &ctx = *con.context;
	// DP (ExtractGetStats) and Post (OJTToLogicalPlan / PK-FK lookup) reach into
	// the catalog, which requires an active transaction — ExtractPlan already
	// committed its own. Drive one manually, as sj_operator_bench does.
	ctx.transaction.BeginTransaction();
	OuterYanPre().Optimize(std::move(plan), *tree); // BuildOT, Simplify, pairs, Desimplify
	OuterYanDP(ctx).Optimize(*tree);                // DP enumeration and OT rebuild
	OuterYanPost(ctx).Optimize(*tree);             // Resimplify (reverts) → lower plan
	ctx.transaction.Commit();
	return tree;
}

//! Drive only the pre-DP phase so tests can inspect the exact semi-join pairs
//! recorded from the simplified OJT. Unlike BuildFullIRFor, this leaves the OT
//! and its base-relation metadata alive.
unique_ptr<OuterYanTree> BuildPreIRFor(Connection &con, const string &sql) {
	REQUIRE_NO_FAIL(con.Query(
	    "SET disabled_optimizers TO "
	    "'outer_yan_pre,outer_yan_dp,outer_yan_post,join_order,"
	    "column_lifetime,statistics_propagation,outer_join_simplification,"
	    "join_elimination'"));
	auto plan = con.ExtractPlan(sql, /*resolve_column_bindings=*/false);
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO ''"));
	REQUIRE(plan);
	auto tree = make_uniq<OuterYanTree>();
	if (!tree->CheckApplicability(*plan)) {
		return tree;
	}
	auto &ctx = *con.context;
	ctx.transaction.BeginTransaction();
	OuterYanPre().Optimize(std::move(plan), *tree);
	ctx.transaction.Commit();
	return tree;
}

RelationId RelationForTable(const OuterYanTree &tree, const string &table_name) {
	for (auto *relation : tree.ot_relations_by_id) {
		if (!relation) {
			continue;
		}
		auto *base = FindBaseOp(relation->origin);
		if (!base || base->type != LogicalOperatorType::LOGICAL_GET) {
			continue;
		}
		auto table = base->Cast<LogicalGet>().GetTable();
		if (table && table->name == table_name) {
			return relation->relation_id;
		}
	}
	throw InternalException("RelationForTable: table %s not found", table_name);
}

bool HasSemiPair(const vector<OuterYanSemiPair> &pairs, RelationId build, RelationId probe) {
	return std::any_of(pairs.begin(), pairs.end(), [&](const OuterYanSemiPair &pair) {
		return pair.build == build && pair.probe == probe;
	});
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

//! Ten-relation seed (a..j) for wide DP-enumeration / breadth cases. Builds on
//! `SeedWide` (a..f) and adds g..j. Keys overlap partially with `a` so outer
//! joins NULL-pad some rows and a few keys fan out (duplicate matches).
void SeedTen(Connection &con) {
	SeedWide(con);
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE g(id INTEGER, gx INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE h(id INTEGER, hx INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE i(id INTEGER, ix INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE j(id INTEGER, jx INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO g VALUES (1, 7), (3, 7), (3, 8), (10, 7)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO h VALUES (2, 40), (4, 40), (5, 50)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO i VALUES (1, 1), (3, 3), (5, 5)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO j VALUES (3, 0), (5, 0), (6, 0)"));
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

	ScopedOuterYanCandidateForce force_candidate;
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO ''"));
	auto optimized = con.Query(sql);
	REQUIRE_FALSE(optimized->HasError());

	REQUIRE(CollectSortedRows(*optimized) == CollectSortedRows(*baseline));
}

string ExplainOptimizedPlan(Connection &con, const string &disabled_optimizers, const string &sql) {
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO '" + disabled_optimizers + "'"));
	auto result = con.Query("EXPLAIN " + sql);
	REQUIRE_FALSE(result->HasError());
	REQUIRE(result->RowCount() == 1);
	return result->GetValue(1, 0).ToString();
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
	// Simplify rebases `original_kind` to the post-Simplify kind (the Desimplify
	// baseline), so after this pass `original_kind == kind` on every edge — the
	// source LEFT is not retained. Observe the collapse via the stage counter plus
	// the resulting INNER edge: every join in this query was LEFT in the source,
	// so an INNER edge can only be Simplify lowering the (a,b) join.
	REQUIRE(tree->stage_stats.simplify_collapses >= 1);
	bool found_inner = false;
	std::function<void(const OJTNode &)> walk = [&](const OJTNode &node) {
		for (const auto &edge : node.children) {
			if (edge.kind == JoinType::INNER) {
				found_inner = true;
			}
			walk(*edge.child);
		}
	};
	walk(tree->OJT().Root());
	REQUIRE(found_inner);
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
	// The b→c chain is deliberately cost-reordered; a star on a.id now takes
	// the no-reorder fallback and correctly contains no SJ operators.
	ScopedOuterYanCandidateForce force_candidate;
	auto result = con.Query("EXPLAIN SELECT a.id, b.bx, c.cx "
	                        "FROM a LEFT JOIN b ON a.id = b.id "
	                        "LEFT JOIN c ON b.id = c.id");
	REQUIRE_FALSE(result->HasError());
	auto plan_text = result->ToString();
	REQUIRE(plan_text.find("SJ_BUILD") != string::npos);
	REQUIRE(plan_text.find("SJ_PROBE") != string::npos);
}

TEST_CASE("outer_yan semi-join elimination: NOT NULL enforced FK makes PK build redundant",
          "[outer_yan][passes][semi][elimination]") {
	DuckDB db(nullptr);
	Connection con(db);
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE dim(k INTEGER PRIMARY KEY)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE fact(id INTEGER PRIMARY KEY, "
	                          "dim_k INTEGER NOT NULL REFERENCES dim(k))"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE opt(fact_id INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO dim VALUES (1), (2)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO fact VALUES (10, 1), (20, 2)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO opt VALUES (10)"));

	const string sql = "SELECT * FROM fact INNER JOIN dim ON fact.dim_k=dim.k "
	                   "LEFT JOIN opt ON fact.id=opt.fact_id";
	auto tree = BuildPreIRFor(con, sql);
	REQUIRE(tree->HasOT());
	const auto fact = RelationForTable(*tree, "fact");
	const auto dim = RelationForTable(*tree, "dim");
	// The enforced FK proves existence and NOT NULL excludes the one SQL value
	// that an FK permits without a referenced PK row, hence fact ⋉ dim = fact.
	REQUIRE_FALSE(HasSemiPair(tree->bottom_up_pairs, dim, fact));
	// The opposite round is not an identity: unreferenced dimension rows may
	// exist. Its presence also proves the INNER edge itself was recorded.
	REQUIRE(HasSemiPair(tree->top_down_pairs, fact, dim));
	AssertOuterYanPreservesResults(con, sql);
}

TEST_CASE("outer_yan semi-join elimination: nullable FK retains PK-to-FK reduction",
          "[outer_yan][passes][semi][elimination]") {
	DuckDB db(nullptr);
	Connection con(db);
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE dim(k INTEGER PRIMARY KEY)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE fact(id INTEGER PRIMARY KEY, "
	                          "dim_k INTEGER REFERENCES dim(k))"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE opt(fact_id INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO dim VALUES (1), (2)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO fact VALUES (10, 1), (20, 2), (30, NULL)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO opt VALUES (10)"));

	const string sql = "SELECT * FROM fact INNER JOIN dim ON fact.dim_k=dim.k "
	                   "LEFT JOIN opt ON fact.id=opt.fact_id";
	auto tree = BuildPreIRFor(con, sql);
	REQUIRE(tree->HasOT());
	const auto fact = RelationForTable(*tree, "fact");
	const auto dim = RelationForTable(*tree, "dim");
	// NULL satisfies the FK constraint but cannot match under equality, so this
	// Round-1 pair is required to reproduce the INNER join's rejection.
	REQUIRE(HasSemiPair(tree->bottom_up_pairs, dim, fact));
	AssertOuterYanPreservesResults(con, sql);
}

TEST_CASE("outer_yan semi-join elimination: NOT NULL without FK retains orphan reduction",
          "[outer_yan][passes][semi][elimination]") {
	DuckDB db(nullptr);
	Connection con(db);
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE dim(k INTEGER PRIMARY KEY)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE fact(id INTEGER PRIMARY KEY, dim_k INTEGER NOT NULL)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE opt(fact_id INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO dim VALUES (1), (2)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO fact VALUES (10, 1), (20, 2), (30, 999)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO opt VALUES (10)"));

	const string sql = "SELECT * FROM fact INNER JOIN dim ON fact.dim_k=dim.k "
	                   "LEFT JOIN opt ON fact.id=opt.fact_id";
	auto tree = BuildPreIRFor(con, sql);
	REQUIRE(tree->HasOT());
	const auto fact = RelationForTable(*tree, "fact");
	const auto dim = RelationForTable(*tree, "dim");
	// NOT NULL proves only that a value exists, not that the value is covered by
	// dim's key. The orphan 999 makes fact ⋉ dim a strict reduction.
	REQUIRE(HasSemiPair(tree->bottom_up_pairs, dim, fact));
	AssertOuterYanPreservesResults(con, sql);
}

TEST_CASE("outer_yan semi-join elimination: nullable probe key survives RIGHT-FULL desimplification",
          "[outer_yan][passes][semi][elimination][bushy5b]") {
	DuckDB db(nullptr);
	Connection con(db);
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE ss(id INTEGER, item_id INTEGER, promo_id INTEGER, cust_id INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE it(item_id INTEGER PRIMARY KEY)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE pr(promo_id INTEGER PRIMARY KEY)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE cu(cust_id INTEGER PRIMARY KEY, addr_id INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE ad(addr_id INTEGER PRIMARY KEY)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO it VALUES (1), (2)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO pr VALUES (10), (20), (30)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO ad VALUES (100), (200), (20000)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO cu VALUES (1000, 100), (2000, 200), (4000, 20000)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO ss VALUES "
	                          "(1, 1, 10, 1000), "
	                          "(2, 2, NULL, 2000), "
	                          "(3, 999, 20, 9999), "
	                          "(4, 1, 999, 1000)"));

	// Reduced form of oy_ds_ds_bushy5b_v0:
	// ((SS LEFT I) RIGHT P) FULL ((C LEFT CA)), followed by a CA predicate.
	// Simplification makes SS-P INNER; desimplification may turn that into a
	// synthetic outer edge, whose correctness depends on retaining P -> SS.
	const string sql =
	    "SELECT ss.id, ss.promo_id, pr.promo_id, cu.cust_id, ad.addr_id "
	    "FROM (((ss LEFT OUTER JOIN it ON ss.item_id=it.item_id) "
	    "RIGHT OUTER JOIN pr ON ss.promo_id=pr.promo_id) "
	    "FULL OUTER JOIN (cu LEFT OUTER JOIN ad ON cu.addr_id=ad.addr_id) "
	    "ON ss.cust_id=cu.cust_id) "
	    "WHERE ad.addr_id > 0 AND ad.addr_id < 10000";

	auto tree = BuildPreIRFor(con, sql);
	REQUIRE(tree->HasOT());
	REQUIRE(tree->stage_stats.simplify_collapses >= 3);
	REQUIRE(tree->stage_stats.desimplify_changes >= 1);
	const auto ss_relation = RelationForTable(*tree, "ss");
	const auto promotion_relation = RelationForTable(*tree, "pr");
	REQUIRE(HasSemiPair(tree->bottom_up_pairs, promotion_relation, ss_relation));

	AssertOuterYanPreservesResults(con, sql);
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO ''"));
	auto optimized = con.Query(sql);
	REQUIRE_FALSE(optimized->HasError());
	const vector<string> expected {
	    "1|10|10|1000|100",
	    "NULL|NULL|NULL|2000|200",
	};
	REQUIRE(CollectSortedRows(*optimized) == expected);
}

TEST_CASE("outer_yan policy: aggregate queries use the exact DuckDB plan",
          "[outer_yan][passes][aggregate_policy]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedPasses(con);
	REQUIRE_NO_FAIL(con.Query("PRAGMA explain_output='optimized_only'"));

	const string root_aggregate =
	    "SELECT a.id, SUM(c.cx) FROM a LEFT JOIN b ON a.id=b.id "
	    "LEFT JOIN c ON b.id=c.id GROUP BY a.id";
	const auto root_baseline = ExplainOptimizedPlan(con, "outer_yan", root_aggregate);
	const auto root_enabled = ExplainOptimizedPlan(con, "", root_aggregate);
	REQUIRE(root_enabled == root_baseline);
	REQUIRE(root_enabled.find("SJ_BUILD") == string::npos);
	REQUIRE(root_enabled.find("SJ_PROBE") == string::npos);

	const string nested_aggregate =
	    "SELECT a.id, b.bx, totals.total FROM a LEFT JOIN b ON a.id=b.id "
	    "LEFT JOIN (SELECT id, SUM(cx) AS total FROM c GROUP BY id) totals "
	    "ON b.id=totals.id";
	const auto nested_baseline = ExplainOptimizedPlan(con, "outer_yan", nested_aggregate);
	const auto nested_enabled = ExplainOptimizedPlan(con, "", nested_aggregate);
	REQUIRE(nested_enabled == nested_baseline);
	REQUIRE(nested_enabled.find("SJ_BUILD") == string::npos);
	REQUIRE(nested_enabled.find("SJ_PROBE") == string::npos);

	const string distinct_query =
	    "SELECT DISTINCT a.id, b.bx, c.cx FROM a LEFT JOIN b ON a.id=b.id "
	    "LEFT JOIN c ON b.id=c.id";
	const auto distinct_baseline = ExplainOptimizedPlan(con, "outer_yan", distinct_query);
	const auto distinct_enabled = ExplainOptimizedPlan(con, "", distinct_query);
	REQUIRE(distinct_enabled == distinct_baseline);
	REQUIRE(distinct_enabled.find("SJ_BUILD") == string::npos);
	REQUIRE(distinct_enabled.find("SJ_PROBE") == string::npos);
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
	// Full SELECT * (every column of both relations) so the rebuilt output
	// schema is exercised in full — partial projections let column pruning hide
	// a reordering/binding defect.
	AssertOuterYanPreservesResults(con, "SELECT * "
	                                     "FROM na LEFT JOIN nb ON na.k = nb.k");
}

TEST_CASE("outer_yan passes: equivalence — 2-relation RIGHT join",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	AssertOuterYanPreservesResults(con, "SELECT * "
	                                     "FROM na RIGHT JOIN nb ON na.k = nb.k");
}

TEST_CASE("outer_yan passes: equivalence — 2-relation FULL OUTER join",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	// Exclusive keys (1,4 vs 6) and NULL keys on both sides surface NULL-padded.
	AssertOuterYanPreservesResults(con, "SELECT * "
	                                     "FROM na FULL OUTER JOIN nb ON na.k = nb.k");
}

TEST_CASE("outer_yan passes: equivalence — 3-relation LEFT chain",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	AssertOuterYanPreservesResults(con, "SELECT * "
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
	AssertOuterYanPreservesResults(con, "SELECT * "
	                                     "FROM nb "
	                                     "RIGHT JOIN na ON na.k = nb.k "
	                                     "LEFT JOIN nc ON na.k = nc.k");
}

TEST_CASE("outer_yan passes: equivalence — FULL OUTER head + LEFT tail",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	AssertOuterYanPreservesResults(con, "SELECT * "
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
	AssertOuterYanPreservesResults(con, "SELECT * "
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
	AssertOuterYanPreservesResults(con, "SELECT * "
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
	AssertOuterYanPreservesResults(con, "SELECT * "
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
	AssertOuterYanPreservesResults(con, "SELECT * "
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
	AssertOuterYanPreservesResults(con, "SELECT * "
	                                     "FROM (na LEFT JOIN nb ON na.k = nb.k) "
	                                     "INNER JOIN (nc INNER JOIN nd ON nc.k = nd.k) "
	                                     "ON na.k = nc.k");
}

TEST_CASE("outer_yan passes: equivalence — full schema incl. null-supplying side",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	// SELECT * forces every column — including the NULL-padded null-supplying
	// side (nb) — through the rebuilt projection cap; the roundtrip must
	// reproduce the exact schema and the NULL padding.
	AssertOuterYanPreservesResults(con, "SELECT * "
	                                     "FROM na LEFT JOIN nb ON na.k = nb.k");
}

TEST_CASE("outer_yan passes: base NOT NULL does not survive outer-join null extension",
          "[outer_yan][passes][equivalence][semi][elimination]") {
	DuckDB db(nullptr);
	Connection con(db);
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE dim(k INTEGER PRIMARY KEY)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE fact(id INTEGER PRIMARY KEY, "
	                          "dim_k INTEGER NOT NULL REFERENCES dim(k))"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE carrier(cid INTEGER, fact_id INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE opt(cid INTEGER)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO dim VALUES (1), (2)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO fact VALUES (10, 1), (20, 2)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO carrier VALUES (100, 10), (200, 99)"));
	REQUIRE_NO_FAIL(con.Query("INSERT INTO opt VALUES (100)"));

	const string sql =
	    "SELECT carrier.cid, fact.id, fact.dim_k, dim.k, opt.cid "
	    "FROM carrier "
	    "LEFT JOIN fact ON carrier.fact_id=fact.id "
	    "LEFT JOIN dim ON fact.dim_k=dim.k "
	    "LEFT JOIN opt ON carrier.cid=opt.cid";
	AssertOuterYanPreservesResults(con, sql);

	// fact.dim_k is NOT NULL at its base scan, but the first LEFT join creates
	// a synthetic NULL fact tuple for carrier 200. That row must survive both
	// later LEFT joins; schema nullability must never be applied to join output.
	REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO ''"));
	auto optimized = con.Query(sql);
	REQUIRE_FALSE(optimized->HasError());
	const vector<string> expected {
	    "100|10|1|1|100",
	    "200|NULL|NULL|NULL|NULL",
	};
	REQUIRE(CollectSortedRows(*optimized) == expected);

	// Keep this an OuterYan execution regression rather than an accidental
	// equality between two ordinary DuckDB plans.
	ScopedOuterYanCandidateForce force_candidate;
	const auto plan = ExplainOptimizedPlan(con, "", sql);
	REQUIRE(plan.find("SJ_PROBE") != string::npos);
}

TEST_CASE("outer_yan passes: equivalence — 5-relation LEFT chain stresses DP enumeration",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedWide(con);
	AssertOuterYanPreservesResults(con, "SELECT * "
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
	AssertOuterYanPreservesResults(con, "SELECT * "
	                                     "FROM a "
	                                     "LEFT JOIN b ON a.id = b.id "
	                                     "LEFT JOIN c ON a.id = c.id "
	                                     "LEFT JOIN d ON a.id = d.id "
	                                     "LEFT JOIN e ON a.id = e.id "
	                                     "LEFT JOIN f ON a.id = f.id");
}

// A unary predicate over a subquery projection — `t.b_total > 150` on
// `b.bx AS b_total` — is folded by filter-pushdown into b's table scan (as
// `b.bx > 150`), not left as a residual filter referencing the projection's
// `table_index`. So `LogicalPlanToOT` sees an ordinary filtered base relation
// and lowers it without error: the pushed-into-scan predicate is handled, not
// rejected. (Scan filters are intentionally *not* treated as null-rejection for
// outer-join simplification — they are applied pre-join — but they are still a
// perfectly valid base relation to build an OT over.)
TEST_CASE("outer_yan passes: predicate folded into scan is handled, not rejected",
          "[outer_yan][passes][equivalence]") {
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
	REQUIRE_NOTHROW(LogicalPlanToOT(std::move(plan), tree));
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

// ============================================================================
// Broader equivalence variants (full SELECT *). Scale the relation count from
// 3 to 10 and mix INNER / LEFT / RIGHT / FULL OUTER in a single skeleton, so
// DP enumeration and the OJT→plan roundtrip are exercised across a wide span of
// shapes. Every query selects every column (`SELECT *`) — the union of all
// joined relations' columns — so column pruning cannot mask a reorder/binding
// defect. Each carries at least one outer join so the applicability gate fires.
// ============================================================================

TEST_CASE("outer_yan passes: equivalence — full SELECT* 3-relation LEFT+INNER",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	AssertOuterYanPreservesResults(con, "SELECT * "
	                                     "FROM a "
	                                     "LEFT JOIN b ON a.id = b.id "
	                                     "INNER JOIN c ON a.id = c.id");
}

TEST_CASE("outer_yan passes: equivalence — full SELECT* 5-relation mixed LEFT/INNER/FULL",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	AssertOuterYanPreservesResults(con, "SELECT * "
	                                     "FROM a "
	                                     "LEFT JOIN b ON a.id = b.id "
	                                     "INNER JOIN c ON a.id = c.id "
	                                     "FULL OUTER JOIN d ON a.id = d.id "
	                                     "LEFT JOIN e ON a.id = e.id");
}

TEST_CASE("outer_yan passes: equivalence — full SELECT* 7-relation mixed incl. RIGHT",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	AssertOuterYanPreservesResults(con, "SELECT * "
	                                     "FROM a "
	                                     "LEFT JOIN b ON a.id = b.id "
	                                     "LEFT JOIN c ON a.id = c.id "
	                                     "INNER JOIN d ON a.id = d.id "
	                                     "LEFT JOIN e ON a.id = e.id "
	                                     "RIGHT JOIN f ON a.id = f.id "
	                                     "LEFT JOIN g ON a.id = g.id");
}

TEST_CASE("outer_yan passes: equivalence — full SELECT* 10-relation LEFT chain",
          "[outer_yan][passes][equivalence]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	AssertOuterYanPreservesResults(con, "SELECT * "
	                                     "FROM a "
	                                     "LEFT JOIN b ON a.id = b.id "
	                                     "LEFT JOIN c ON a.id = c.id "
	                                     "LEFT JOIN d ON a.id = d.id "
	                                     "LEFT JOIN e ON a.id = e.id "
	                                     "LEFT JOIN f ON a.id = f.id "
	                                     "LEFT JOIN g ON a.id = g.id "
	                                     "LEFT JOIN h ON a.id = h.id "
	                                     "LEFT JOIN i ON a.id = i.id "
	                                     "LEFT JOIN j ON a.id = j.id");
}

// ============================================================================
// Broader aggregate-policy variants over 3..6-relation outer-join skeletons.
// These verify ON/OFF result equivalence while the production policy routes
// every aggregate query through DuckDB's normal optimizer.
// ============================================================================

TEST_CASE("outer_yan policy: COUNT(*) over 3-relation LEFT chain stays on DuckDB",
          "[outer_yan][passes][equivalence][aggregate_policy]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	AssertOuterYanPreservesResults(con, "SELECT COUNT(*) "
	                                     "FROM a "
	                                     "LEFT JOIN b ON a.id = b.id "
	                                     "LEFT JOIN c ON a.id = c.id");
}

TEST_CASE("outer_yan policy: GROUP BY + SUM over LEFT chain stays on DuckDB",
          "[outer_yan][passes][equivalence][aggregate_policy]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	AssertOuterYanPreservesResults(con, "SELECT a.id, SUM(c.cx) "
	                                     "FROM a "
	                                     "LEFT JOIN b ON a.id = b.id "
	                                     "LEFT JOIN c ON a.id = c.id "
	                                     "GROUP BY a.id");
}

TEST_CASE("outer_yan policy: GROUP BY + COUNT/MIN/MAX stays on DuckDB",
          "[outer_yan][passes][equivalence][aggregate_policy]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	AssertOuterYanPreservesResults(con, "SELECT a.id, COUNT(b.bx), MIN(c.cx), MAX(d.dx) "
	                                     "FROM a "
	                                     "LEFT JOIN b ON a.id = b.id "
	                                     "INNER JOIN c ON a.id = c.id "
	                                     "FULL OUTER JOIN d ON a.id = d.id "
	                                     "GROUP BY a.id");
}

TEST_CASE("outer_yan policy: SUM over 6-relation chain stays on DuckDB",
          "[outer_yan][passes][equivalence][aggregate_policy]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	AssertOuterYanPreservesResults(con, "SELECT SUM(f.fx) "
	                                     "FROM a "
	                                     "LEFT JOIN b ON a.id = b.id "
	                                     "LEFT JOIN c ON a.id = c.id "
	                                     "LEFT JOIN d ON a.id = d.id "
	                                     "LEFT JOIN e ON a.id = e.id "
	                                     "LEFT JOIN f ON a.id = f.id");
}

// ============================================================================
// Pipeline-stage transformation verification (item 4). Every OuterYan pass
// records what it changed in `OuterYanTree::stage_stats`; these tests assert a
// stage actually fired (not silently no-op'd) on a query crafted to trigger it,
// so a future refactor that quietly drops a transform is caught here.
//   - `BuildIRFor`     stops after Simplify; the OJT is still inspectable.
//   - `BuildFullIRFor` runs the whole Pre→DP→Post pipeline; the OJT is consumed,
//                      but the StageStats counters survive on the tree.
// ============================================================================

namespace {
//! True iff some OJT edge satisfies `pred(kind, original_kind)`.
bool AnyEdge(const OJTNode &root,
             const std::function<bool(OuterYanJoinKind, OuterYanJoinKind)> &pred) {
	bool hit = false;
	std::function<void(const OJTNode &)> walk = [&](const OJTNode &node) {
		for (const auto &edge : node.children) {
			if (pred(edge.kind, edge.original_kind)) {
				hit = true;
			}
			walk(*edge.child);
		}
	};
	walk(root);
	return hit;
}
} // namespace

// ---- 4a Simplification: OUTER kinds collapse under null-rejection -----------

TEST_CASE("outer_yan passes: Simplify — FULL OUTER → one-sided when only one side null-rejected",
          "[outer_yan][passes][simplify]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	// `na.v > 0` rejects NULL on the left (preserved) side only; FULL OUTER loses
	// right-preservation, becoming a one-sided outer (LEFT, or RIGHT if the OJT
	// flips parent orientation) — but NOT all the way to INNER.
	auto tree = BuildIRFor(con,
	    "SELECT * FROM na FULL OUTER JOIN nb ON na.k = nb.k WHERE na.v > 0");
	REQUIRE(tree->HasOJT());
	REQUIRE(tree->stage_stats.simplify_collapses >= 1);
	// Simplify rebases `original_kind` to the post-Simplify kind, so assert on the
	// resulting kind: a FULL OUTER with only the left side null-rejected collapses
	// to a one-sided outer (LEFT, or RIGHT if the OJT flips parent orientation),
	// but not all the way to INNER.
	REQUIRE(AnyEdge(tree->OJT().Root(), [](OuterYanJoinKind k, OuterYanJoinKind) {
		return k == JoinType::LEFT || k == JoinType::RIGHT;
	}));
}

TEST_CASE("outer_yan passes: Simplify — FULL OUTER → INNER when both sides null-rejected",
          "[outer_yan][passes][simplify]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	// Two single-relation predicates (LogicalFilter splits the AND); both reject
	// NULL, so both sides are preserved and FULL collapses straight to INNER.
	auto tree = BuildIRFor(con,
	    "SELECT * FROM na FULL OUTER JOIN nb ON na.k = nb.k WHERE na.v > 0 AND nb.v > 0");
	REQUIRE(tree->HasOJT());
	REQUIRE(tree->stage_stats.simplify_collapses >= 1);
	// Simplify rebases `original_kind` to the post-Simplify kind, so assert on the
	// resulting kind: both sides null-rejected ⇒ FULL OUTER collapses to INNER.
	REQUIRE(AnyEdge(tree->OJT().Root(), [](OuterYanJoinKind k, OuterYanJoinKind) {
		return k == JoinType::INNER;
	}));
}

TEST_CASE("outer_yan passes: Simplify — no collapse when no predicate rejects NULL",
          "[outer_yan][passes][simplify]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedNullable(con);
	auto tree = BuildIRFor(con, "SELECT * FROM na LEFT JOIN nb ON na.k = nb.k");
	REQUIRE(tree->HasOJT());
	REQUIRE(tree->stage_stats.simplify_collapses == 0);
}

// ---- Exploration probe: print StageStats across many shapes (hidden) --------
// Run explicitly with: unittest "[outer_yan][stagestats]". Used to pin down
// which query shapes drive Desimplify / DP-reorder / Resimplify before those
// stages get hard assertions below.
TEST_CASE("outer_yan passes: StageStats probe across shapes (DIAGNOSTIC)",
          "[outer_yan][passes][stagestats][.]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	const char *queries[] = {
	    "SELECT * FROM a LEFT JOIN b ON a.id=b.id LEFT JOIN c ON a.id=c.id",
	    "SELECT * FROM a LEFT JOIN b ON a.id=b.id INNER JOIN c ON a.id=c.id",
	    "SELECT * FROM a INNER JOIN b ON a.id=b.id LEFT JOIN c ON a.id=c.id",
	    "SELECT * FROM a INNER JOIN b ON a.id=b.id LEFT JOIN c ON a.id=c.id FULL OUTER JOIN d ON a.id=d.id",
	    "SELECT * FROM a FULL OUTER JOIN b ON a.id=b.id LEFT JOIN c ON a.id=c.id",
	    "SELECT * FROM a LEFT JOIN b ON a.id=b.id RIGHT JOIN c ON a.id=c.id",
	    "SELECT * FROM a LEFT JOIN b ON a.id=b.id LEFT JOIN c ON b.id=c.id",
	    "SELECT * FROM a LEFT JOIN b ON a.id=b.id INNER JOIN c ON b.id=c.id",
	    "SELECT * FROM a LEFT JOIN b ON a.id=b.id LEFT JOIN c ON a.id=c.id "
	    "LEFT JOIN d ON a.id=d.id LEFT JOIN e ON a.id=e.id",
	    "SELECT * FROM a INNER JOIN b ON a.id=b.id FULL OUTER JOIN c ON b.id=c.id",
	};
	std::printf("\n%-72s %5s %5s %5s\n", "query", "simp", "desi", "resi");
	for (const auto *q : queries) {
		auto tree = BuildFullIRFor(con, q);
		const auto &s = tree->stage_stats;
		std::printf("%-72s %5llu %5llu %5llu\n", string(q).substr(0, 72).c_str(),
		            (unsigned long long)s.simplify_collapses,
		            (unsigned long long)s.desimplify_changes,
		            (unsigned long long)s.resimplify_reverts);
	}
}

// ---- 4b Desimplification: a join kind IS rewritten when associativity needs it.
// NOTE on the user's "no inner join remains" expectation: that is NOT a universal
// invariant of these rules — an INNER (P,D) pair already in an OK associativity
// cell (e.g. INNER under INNER/LEFT) is left as INNER. The provable, enforced
// post-condition is `Desimplification::AllPairsSatisfy` (every (P,D) pair lands
// in an OK cell), which OuterYanPre::Optimize already throws on if violated.
// This test pins the weaker, always-true fact: a query whose simplified tree has
// a non-OK mix forces at least one committed rewrite.
TEST_CASE("outer_yan passes: Desimplify — INNER under FULL OUTER forces a rewrite",
          "[outer_yan][passes][desimplify]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	const string sql = "SELECT * FROM a INNER JOIN b ON a.id=b.id "
	                   "FULL OUTER JOIN c ON b.id=c.id";
	auto tree = BuildFullIRFor(con, sql);
	REQUIRE(tree->stage_stats.desimplify_changes >= 1);
	// The rewrite must preserve results.
	AssertOuterYanPreservesResults(con, sql);
}

// ---- 4c DP: the cost model restructures the join tree (not a pass-through).
TEST_CASE("outer_yan passes: DP — cost model restructures the join order",
          "[outer_yan][passes][dp]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	// LEFT (a,b) then LEFT (b,c): the cost-chosen materialised order differs
	// structurally from the written order. Compare the stable grouping
	// signatures directly; this is a test concern, not persistent stage state.
	auto tree = BuildIRFor(con, "SELECT * FROM a LEFT JOIN b ON a.id=b.id LEFT JOIN c ON b.id=c.id");
	const auto input_signature = OuterYanDP::JoinGroupingSignature(*tree);
	auto &ctx = *con.context;
	ctx.transaction.BeginTransaction();
	auto summary = OuterYanDP(ctx).Optimize(*tree);
	ctx.transaction.Commit();
	REQUIRE(summary.has_complete_plan);
	REQUIRE(OuterYanDP::JoinGroupingSignature(*tree) != input_signature);
}

TEST_CASE("outer_yan passes: DP — full inner reduction bounds every intermediate",
          "[outer_yan][passes][dp][cost]") {
	DuckDB db(nullptr);
	Connection con(db);
	REQUIRE_NO_FAIL(con.Query(
	    "CREATE TABLE title AS SELECT i % 1876 AS id FROM range(2528) tbl(i)"));
	REQUIRE_NO_FAIL(con.Query(
	    "CREATE TABLE cast_info AS SELECT i % 2079 AS movie_id, i % 1746 AS person_id "
	    "FROM range(36244) tbl(i)"));
	REQUIRE_NO_FAIL(con.Query(
	    "CREATE TABLE name AS SELECT i % 3607 AS id FROM range(4168) tbl(i)"));
	REQUIRE_NO_FAIL(con.Query(
	    "CREATE TABLE aka_name AS SELECT 10 + (i % 285) AS person_id FROM range(901) tbl(i)"));
	REQUIRE_NO_FAIL(con.Query("ANALYZE"));

	const string sql =
	    "SELECT * FROM title t INNER JOIN "
	    "(cast_info ci LEFT JOIN (name n FULL JOIN aka_name an ON n.id = an.person_id) "
	    "ON ci.person_id = n.id) ON t.id = ci.movie_id WHERE an.person_id >= 10";
	auto tree = BuildPreIRFor(con, sql);
	REQUIRE(tree->HasOT());
	auto &ctx = *con.context;
	ctx.transaction.BeginTransaction();
	auto summary = OuterYanDP(ctx).Optimize(*tree);
	ctx.transaction.Commit();
	REQUIRE(summary.has_complete_plan);
	REQUIRE(summary.candidate_join_breakdown.steps.size() == 3);

	bool observed_active_bound = false;
	for (const auto &step : summary.candidate_join_breakdown.steps) {
		REQUIRE(step.join_kind == JoinType::INNER);
		const auto lower_bound = MaxValue(step.left_cardinality, step.right_cardinality);
		REQUIRE(step.output >= lower_bound);
		if (lower_bound > 4.0 * MinValue(step.left_cardinality, step.right_cardinality) &&
		    step.output == lower_bound) {
			observed_active_bound = true;
		}
	}
	REQUIRE(observed_active_bound);
}

TEST_CASE("outer_yan policy: uncertain tiny filter without reduction keeps DuckDB",
          "[outer_yan][policy][cost]") {
	DuckDB db(nullptr);
	Connection con(db);
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE region AS SELECT i AS r_regionkey FROM range(5) tbl(i)"));
	REQUIRE_NO_FAIL(con.Query(
	    "CREATE TABLE nation AS SELECT i AS n_nationkey, i % 5 AS n_regionkey FROM range(25) tbl(i)"));
	REQUIRE_NO_FAIL(con.Query(
	    "CREATE TABLE supplier AS SELECT i AS s_suppkey, i % 25 AS s_nationkey FROM range(1000) tbl(i)"));
	REQUIRE_NO_FAIL(con.Query(
	    "CREATE TABLE partsupp AS SELECT i % 700 AS ps_suppkey FROM range(80000) tbl(i)"));
	REQUIRE_NO_FAIL(con.Query("ANALYZE"));

	const string sql =
	    "SELECT * FROM ((region RIGHT JOIN nation ON r_regionkey = n_regionkey) "
	    "INNER JOIN (supplier FULL JOIN partsupp ON s_suppkey = ps_suppkey) "
	    "ON n_nationkey = s_nationkey) WHERE n_nationkey % 7 <> 0";
	const auto gated_plan = ExplainOptimizedPlan(con, "", sql);
	REQUIRE(gated_plan.find("SJ_BUILD") == string::npos);
	REQUIRE(gated_plan.find("SJ_PROBE") == string::npos);

	ScopedOuterYanCandidateForce force_candidate;
	const auto forced_plan = ExplainOptimizedPlan(con, "", sql);
	REQUIRE(forced_plan.find("SJ_BUILD") != string::npos);
	REQUIRE(forced_plan.find("SJ_PROBE") != string::npos);
}

// ---- 4d Resimplification: a de-simplified edge reverts; the flag is recorded.
TEST_CASE("outer_yan passes: Resimplify — de-simplified edge reverts (flag recorded)",
          "[outer_yan][passes][resimplify]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	// Same mixed INNER/FULL shape that drove the Desimplify rewrite above: after
	// DP the chosen ordering makes that rewrite redundant, so Resimplify reverts
	// the edge to its original kind and records it (item 4d "record such flag").
	const string sql = "SELECT * FROM a INNER JOIN b ON a.id=b.id "
	                   "FULL OUTER JOIN c ON b.id=c.id";
	auto tree = BuildFullIRFor(con, sql);
	REQUIRE(tree->stage_stats.resimplify_reverts >= 1);
	AssertOuterYanPreservesResults(con, sql);
}

// ---- 4e Semi-join insertion: pairs are recorded against the SIMPLIFIED tree
// and are well-formed. Direction 1 of the user's ask — OuterYanPre records the
// pairs from `tree.ConstructOJT()` taken right after Simplify but BEFORE
// Desimplify (outer_yan_pre.cpp), so the pairs only ever reflect the simplified
// tree; a later Desimplify rewrite cannot retroactively alter a recorded pair.
// Direction 2 (the operators actually execute and filter) is covered by the
// EXPLAIN SJ_BUILD/SJ_PROBE assertion ("semi-join pair recording populates both
// phases") plus every on-vs-off equivalence case — the reduction preserves the
// result multiset, which is only possible if the probe actually filters.
TEST_CASE("outer_yan passes: SemijoinInsert — pairs recorded vs simplified tree, well-formed",
          "[outer_yan][passes][semi]") {
	DuckDB db(nullptr);
	Connection con(db);
	SeedTen(con);
	// LEFT (a,b) + INNER (a,c): the INNER edge fires in BOTH Yannakakis sweeps,
	// the LEFT edge fires top-down — so both pair vectors are populated.
	auto tree = BuildFullIRFor(con,
	    "SELECT * FROM a LEFT JOIN b ON a.id=b.id INNER JOIN c ON a.id=c.id");
	const idx_t n = tree->table_to_relation.size();
	REQUIRE(n == 3);
	REQUIRE_FALSE(tree->bottom_up_pairs.empty()); // the INNER edge
	REQUIRE_FALSE(tree->top_down_pairs.empty());  // INNER + LEFT edges
	auto well_formed = [&](const vector<OuterYanSemiPair> &pairs) {
		for (const auto &p : pairs) {
			REQUIRE(p.build < n);
			REQUIRE(p.probe < n);
			REQUIRE(p.build != p.probe);
			REQUIRE_FALSE(p.keys.empty());
		}
	};
	well_formed(tree->bottom_up_pairs);
	well_formed(tree->top_down_pairs);
}
