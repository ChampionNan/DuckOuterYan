// test/optimizer/outer_yan/sj_operator_bench.cpp
//
// Benchmark: PhysicalSJBuild/PhysicalSJProbe vs. DuckDB's plain hash join
// on TPC-H and TPC-DS outer-join query patterns.
//
// Strategy — Option 3 (direct physical plan construction):
//   For each (query, mode) pair this test manually drives the full pipeline:
//     Parser → Planner → Optimizer → PhysicalPlanGenerator
//   walks the resulting PhysicalPlan tree to verify SJ operator presence,
//   and times execution through con.Query() (the Executor is bound to the
//   ClientContext result-collector machinery and cannot be driven independently;
//   see executor.hpp::Initialize and QueryProfiler::StartPhase guards).
//
// Modes
//   BITMAP    disabled_optimizers=''; outer_yan_bitmap_max_bytes=16777216
//   HASH      disabled_optimizers=''; outer_yan_bitmap_max_bytes=0
//   BASELINE  disabled_optimizers='outer_yan_pre,outer_yan_dp,outer_yan_post'
//
// Test tiers
//   [outer_yan][sj_bench]            sf=0 schema-only: plan shape + EXCEPT ALL
//                                    parity. Runs in the default [outer_yan] suite.
//   [sj_bench_slow][.]               sf=0.01: wall-clock timing + speedup table.
//                                    Hidden ([.]) so it is opt-in only — run with
//                                    `unittest "[sj_bench_slow]"`. NOT tagged
//                                    [outer_yan], so the default suite never drags
//                                    in dbgen/dsdgen (which previously hung it).

#include "catch.hpp"
#include "test_helpers.hpp"

#include "duckdb/execution/physical_plan_generator.hpp"
#include "duckdb/main/client_context.hpp"
#include "duckdb/optimizer/optimizer.hpp"
#include "duckdb/parser/parser.hpp"
#include "duckdb/planner/planner.hpp"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <string>
#include <vector>

using namespace duckdb;
using Clock = std::chrono::high_resolution_clock;

// ── Mode control ─────────────────────────────────────────────────────────────

enum class SJMode { BITMAP, HASH, BASELINE };

static const char *ModeName(SJMode m) {
    switch (m) {
    case SJMode::BITMAP:   return "BITMAP";
    case SJMode::HASH:     return "HASH";
    case SJMode::BASELINE: return "BASELINE";
    }
    return "";
}

static void Apply(Connection &con, SJMode mode) {
    switch (mode) {
    case SJMode::BITMAP:
        REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO ''"));
        REQUIRE_NO_FAIL(con.Query("SET VARIABLE outer_yan_bitmap_max_bytes = 16777216"));
        break;
    case SJMode::HASH:
        REQUIRE_NO_FAIL(con.Query("SET disabled_optimizers TO ''"));
        REQUIRE_NO_FAIL(con.Query("SET VARIABLE outer_yan_bitmap_max_bytes = 0"));
        break;
    case SJMode::BASELINE:
        REQUIRE_NO_FAIL(con.Query(
            "SET disabled_optimizers TO 'outer_yan_pre,outer_yan_dp,outer_yan_post'"));
        REQUIRE_NO_FAIL(con.Query("SET VARIABLE outer_yan_bitmap_max_bytes = 16777216"));
        break;
    }
}

// ── Direct physical plan construction ────────────────────────────────────────

// Drives Parser → Planner → Optimizer → PhysicalPlanGenerator for `sql`
// under the current session settings. Wraps the catalog-access phase in a
// manual transaction (required by Planner). QueryProfiler::StartPhase guards
// on !IsEnabled() so calling this outside a query context is safe.
static unique_ptr<PhysicalPlan> BuildPhysicalPlan(ClientContext &ctx,
                                                   const string &sql) {
    Parser parser;
    parser.ParseQuery(sql);
    D_ASSERT(!parser.statements.empty());

    ctx.transaction.BeginTransaction();
    Planner planner(ctx);
    planner.CreatePlan(std::move(parser.statements[0]));
    auto logical = std::move(planner.plan);

    Optimizer optimizer(*planner.binder, ctx);
    logical = optimizer.Optimize(std::move(logical));

    PhysicalPlanGenerator phys_gen(ctx);
    auto plan = phys_gen.Plan(std::move(logical));
    ctx.transaction.Commit();
    return plan;
}

// Walk children (ArenaLinkedList<reference<PhysicalOperator>>); return true if
// any node matches `target`. PhysicalSJBuild is wired via
// PhysicalSJProbe::related_sj_build (not children), so this finds SJ_PROBE;
// SJ_PROBE presence is the correct gate for "SJ operators active".
static bool HasPhysOp(const PhysicalOperator &op, PhysicalOperatorType target) {
    if (op.type == target) {
        return true;
    }
    for (const auto &child_ref : op.children) {
        if (HasPhysOp(child_ref.get(), target)) {
            return true;
        }
    }
    return false;
}

// ── Plan shape assertions ─────────────────────────────────────────────────────

static void RequireSJProbe(Connection &con, const string &sql, SJMode mode) {
    Apply(con, mode);
    auto plan = BuildPhysicalPlan(*con.context, sql);
    INFO(ModeName(mode) << ": SJ_PROBE absent in plan — query: " << sql.substr(0, 60));
    REQUIRE(HasPhysOp(plan->Root(), PhysicalOperatorType::SJ_PROBE));
}

static void RequireNoSJProbe(Connection &con, const string &sql) {
    Apply(con, SJMode::BASELINE);
    auto plan = BuildPhysicalPlan(*con.context, sql);
    INFO("BASELINE: SJ_PROBE unexpectedly present — query: " << sql.substr(0, 60));
    REQUIRE_FALSE(HasPhysOp(plan->Root(), PhysicalOperatorType::SJ_PROBE));
}

// ── Result parity ─────────────────────────────────────────────────────────────

// Materialise `sql` under mode_a and mode_b into temp tables, then verify
// EXCEPT ALL = 0 in both directions.
static void CheckParity(Connection &con, const string &sql,
                         SJMode mode_a, SJMode mode_b, const string &label) {
    Apply(con, mode_a);
    REQUIRE_NO_FAIL(con.Query("CREATE TEMP TABLE _sj_pa AS " + sql));
    Apply(con, mode_b);
    REQUIRE_NO_FAIL(con.Query("CREATE TEMP TABLE _sj_pb AS " + sql));

    auto fwd = con.Query(
        "SELECT COUNT(*) FROM (SELECT * FROM _sj_pa EXCEPT ALL SELECT * FROM _sj_pb)");
    REQUIRE_FALSE(fwd->HasError());
    INFO(ModeName(mode_a) << " vs " << ModeName(mode_b) << " fwd parity: " << label);
    REQUIRE(fwd->Fetch()->GetValue(0, 0).GetValue<int64_t>() == 0);

    auto rev = con.Query(
        "SELECT COUNT(*) FROM (SELECT * FROM _sj_pb EXCEPT ALL SELECT * FROM _sj_pa)");
    REQUIRE_FALSE(rev->HasError());
    INFO(ModeName(mode_b) << " vs " << ModeName(mode_a) << " rev parity: " << label);
    REQUIRE(rev->Fetch()->GetValue(0, 0).GetValue<int64_t>() == 0);

    REQUIRE_NO_FAIL(con.Query("DROP TABLE _sj_pa"));
    REQUIRE_NO_FAIL(con.Query("DROP TABLE _sj_pb"));
}

// ── Timing ────────────────────────────────────────────────────────────────────

static double TimeMin(Connection &con, const string &sql, int runs) {
    double best = std::numeric_limits<double>::max();
    for (int i = 0; i < runs; ++i) {
        auto t0 = Clock::now();
        auto r = con.Query(sql);
        double elapsed = std::chrono::duration<double>(Clock::now() - t0).count();
        REQUIRE_FALSE(r->HasError());
        best = std::min(best, elapsed);
    }
    return best;
}

struct BenchRow {
    std::string label;
    double bitmap_s, hash_s, base_s;
};

static void PrintTable(const std::vector<BenchRow> &rows) {
    std::printf("\n%-52s  %8s  %8s  %9s  %8s  %8s\n",
                "Query", "Bmp(s)", "Hash(s)", "Base(s)", "SpBmp", "SpHash");
    std::printf("%-52s  %8s  %8s  %9s  %8s  %8s\n",
                std::string(52, '-').c_str(),
                "--------", "--------", "---------", "--------", "--------");
    for (auto &r : rows) {
        std::printf("%-52s  %8.4f  %8.4f  %9.4f  %7.2fx  %7.2fx\n",
                    r.label.substr(0, 52).c_str(), r.bitmap_s, r.hash_s, r.base_s,
                    r.base_s / r.bitmap_s, r.base_s / r.hash_s);
    }
    std::printf("\nSpeedup = baseline / mode  (>1x = SJ operators faster)\n\n");
}

// ── Query tables ──────────────────────────────────────────────────────────────

struct BenchCase {
    const char *name;
    const char *sql;
};

// TPC-H outer-join rewrites (same patterns as perf_compare.py).
static const BenchCase TPCH_CASES[] = {
    {"TH-Q1 customer→orders→lineitem",
     "SELECT c_custkey, COUNT(o_orderkey), SUM(l_extendedprice) "
     "FROM customer "
     "LEFT JOIN orders   ON c_custkey  = o_custkey "
     "LEFT JOIN lineitem ON o_orderkey = l_orderkey "
     "GROUP BY c_custkey"},
    {"TH-Q2 nation→supplier→lineitem",
     "SELECT n_name, COUNT(s_suppkey), COUNT(l_linenumber), SUM(l_quantity) "
     "FROM nation "
     "LEFT JOIN supplier ON n_nationkey = s_nationkey "
     "LEFT JOIN lineitem ON s_suppkey   = l_suppkey "
     "GROUP BY n_name"},
    {"TH-Q3 customer→orders→lineitem (mktsegment filter)",
     "SELECT c_custkey, COUNT(o_orderkey), "
     "SUM(l_extendedprice * (1 - l_discount)) AS net_revenue "
     "FROM customer "
     "LEFT JOIN orders   ON c_custkey  = o_custkey "
     "LEFT JOIN lineitem ON o_orderkey = l_orderkey "
     "WHERE c_mktsegment = 'BUILDING' GROUP BY c_custkey"},
    {"TH-Q4 customer→orders→lineitem→supplier (4-way)",
     "SELECT c_custkey, COUNT(DISTINCT o_orderkey), "
     "COUNT(DISTINCT l_linenumber), COUNT(DISTINCT s_suppkey) "
     "FROM customer "
     "LEFT JOIN orders   ON c_custkey  = o_custkey "
     "LEFT JOIN lineitem ON o_orderkey = l_orderkey "
     "LEFT JOIN supplier ON l_suppkey  = s_suppkey "
     "GROUP BY c_custkey"},
    {"TH-Q5 partsupp→part→supplier",
     "SELECT ps_partkey, COUNT(DISTINCT ps_suppkey), "
     "SUM(ps_availqty), MIN(ps_supplycost) "
     "FROM partsupp "
     "LEFT JOIN part     ON ps_partkey = p_partkey "
     "LEFT JOIN supplier ON ps_suppkey = s_suppkey "
     "GROUP BY ps_partkey"},
};

// TPC-DS outer-join star/snowflake patterns (same as tpcds_semi_join_comparison.test).
static const BenchCase TPCDS_CASES[] = {
    {"DS-Q1 date_dim→store_sales→item (q03 pattern)",
     "SELECT d_year, i_brand_id, i_brand, "
     "COUNT(ss_ticket_number), SUM(ss_ext_sales_price) "
     "FROM date_dim "
     "LEFT JOIN store_sales ON d_date_sk  = ss_sold_date_sk "
     "LEFT JOIN item        ON ss_item_sk = i_item_sk "
     "GROUP BY d_year, i_brand_id, i_brand"},
    {"DS-Q2 customer→store_sales→date_dim",
     "SELECT c_customer_sk, COUNT(ss_ticket_number), "
     "SUM(ss_sales_price), COUNT(DISTINCT d_year) "
     "FROM customer "
     "LEFT JOIN store_sales ON c_customer_sk   = ss_customer_sk "
     "LEFT JOIN date_dim    ON ss_sold_date_sk = d_date_sk "
     "GROUP BY c_customer_sk"},
    {"DS-Q3 catalog_sales→customer→date_dim→item (4-way)",
     "SELECT cs_order_number, COUNT(*), COUNT(c_customer_sk), "
     "COUNT(d_date_sk), SUM(cs_net_profit), SUM(cs_sales_price) "
     "FROM catalog_sales "
     "LEFT JOIN customer ON cs_bill_customer_sk = c_customer_sk "
     "LEFT JOIN date_dim ON cs_sold_date_sk     = d_date_sk "
     "LEFT JOIN item     ON cs_item_sk          = i_item_sk "
     "GROUP BY cs_order_number"},
    {"DS-Q4 cd→store_sales→dim→item→promo (5-way, q07 pattern)",
     "SELECT i_item_id, avg(ss_quantity), avg(ss_list_price), "
     "avg(ss_coupon_amt), avg(ss_sales_price) "
     "FROM customer_demographics "
     "LEFT JOIN store_sales ON cd_demo_sk      = ss_cdemo_sk "
     "LEFT JOIN date_dim    ON ss_sold_date_sk = d_date_sk "
     "LEFT JOIN item        ON ss_item_sk      = i_item_sk "
     "LEFT JOIN promotion   ON ss_promo_sk     = p_promo_sk "
     "WHERE cd_gender = 'F' AND cd_marital_status = 'W' "
     "AND cd_education_status = 'Primary' AND d_year = 1998 "
     "GROUP BY i_item_id"},
};

// ─────────────────────────────────────────────────────────────────────────────
// Fast tier: plan shape + EXCEPT ALL parity (sf=0, empty results)
// ─────────────────────────────────────────────────────────────────────────────

TEST_CASE("sj_bench: TPC-H plan shape and result parity (sf=0)",
          "[outer_yan][sj_bench][tpch]") {
    DuckDB db(nullptr);
    if (!db.ExtensionIsLoaded("tpch")) {
        return;
    }
    Connection con(db);
    REQUIRE_NO_FAIL(con.Query("CALL dbgen(sf=0)"));

    for (const auto &c : TPCH_CASES) {
        const string sql(c.sql);
        DYNAMIC_SECTION(c.name) {
            RequireSJProbe(con, sql, SJMode::BITMAP);
            RequireSJProbe(con, sql, SJMode::HASH);
            RequireNoSJProbe(con, sql);
            CheckParity(con, sql, SJMode::BITMAP, SJMode::HASH,     c.name);
            CheckParity(con, sql, SJMode::BITMAP, SJMode::BASELINE, c.name);
        }
    }
}

TEST_CASE("sj_bench: TPC-DS plan shape and result parity (sf=0)",
          "[outer_yan][sj_bench][tpcds]") {
    DuckDB db(nullptr);
    if (!db.ExtensionIsLoaded("tpcds")) {
        return;
    }
    Connection con(db);
    REQUIRE_NO_FAIL(con.Query("CALL dsdgen(sf=0)"));

    for (const auto &c : TPCDS_CASES) {
        const string sql(c.sql);
        DYNAMIC_SECTION(c.name) {
            RequireSJProbe(con, sql, SJMode::BITMAP);
            RequireSJProbe(con, sql, SJMode::HASH);
            RequireNoSJProbe(con, sql);
            CheckParity(con, sql, SJMode::BITMAP, SJMode::HASH,     c.name);
            CheckParity(con, sql, SJMode::BITMAP, SJMode::BASELINE, c.name);
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Slow tier: execution timing + speedup table (run explicitly with [sj_bench_slow])
// ─────────────────────────────────────────────────────────────────────────────

TEST_CASE("sj_bench: TPC-H execution timing (sf=0.01)",
          "[sj_bench_slow][tpch][.]") {
    DuckDB db(nullptr);
    if (!db.ExtensionIsLoaded("tpch")) {
        return;
    }
    Connection con(db);
    REQUIRE_NO_FAIL(con.Query("CALL dbgen(sf=0.01)"));
    constexpr int N = 5;

    std::vector<BenchRow> rows;
    for (const auto &c : TPCH_CASES) {
        const string sql(c.sql);
        Apply(con, SJMode::BITMAP);   double t_bmp  = TimeMin(con, sql, N);
        Apply(con, SJMode::HASH);     double t_hash = TimeMin(con, sql, N);
        Apply(con, SJMode::BASELINE); double t_base = TimeMin(con, sql, N);
        rows.push_back({c.name, t_bmp, t_hash, t_base});
    }
    PrintTable(rows);
}

TEST_CASE("sj_bench: TPC-DS execution timing (sf=0.01)",
          "[sj_bench_slow][tpcds][.]") {
    DuckDB db(nullptr);
    if (!db.ExtensionIsLoaded("tpcds")) {
        return;
    }
    Connection con(db);
    REQUIRE_NO_FAIL(con.Query("CALL dsdgen(sf=0.01)"));
    constexpr int N = 5;

    std::vector<BenchRow> rows;
    for (const auto &c : TPCDS_CASES) {
        const string sql(c.sql);
        Apply(con, SJMode::BITMAP);   double t_bmp  = TimeMin(con, sql, N);
        Apply(con, SJMode::HASH);     double t_hash = TimeMin(con, sql, N);
        Apply(con, SJMode::BASELINE); double t_base = TimeMin(con, sql, N);
        rows.push_back({c.name, t_bmp, t_hash, t_base});
    }
    PrintTable(rows);
}

// ─────────────────────────────────────────────────────────────────────────────
// Selectivity sweep: BITMAP vs HASH vs BASELINE as the semi-join's filtering
// power varies from p=0 (drops everything) to p=1 (drops nothing). Synthetic,
// self-contained (no TPC extension needed), so it isolates the separated
// semi-join's runtime effect from query-specific noise — directly answering
// "vary the predicates from 0 to 1, with detailed statistics and the query
// setting". Tune N / DOM to vary data scale; the join key is fact.k.
//
//   fact(k,v)  : N rows, key k = i mod DOM (uniform over the domain).
//   dimA(k)    : keys [0, keep) with keep = round(p*DOM) — the INNER join
//                fact⋈dimA keeps exactly the p fraction of fact whose key < keep.
//   dimB(k)    : full domain [0, DOM); the LEFT join fact⟕dimB adds no rows but
//                makes the query OuterYan-applicable (acyclic, one outer join).
//
// The separated SJ build-on-dimA / probe-on-fact pre-reduces fact before the
// hash join; the speedup over BASELINE is expected to peak at small p.
TEST_CASE("sj_bench: selectivity sweep (synthetic, predicate fraction p=0..1)",
          "[sj_bench_slow][selectivity][.]") {
    DuckDB db(nullptr);
    Connection con(db);
    constexpr int64_t N    = 300000; // fact rows   (raise to scale data up)
    constexpr int64_t DOM  = 100000; // key domain  (raise to scale keys up)
    constexpr int     RUNS = 5;

    REQUIRE_NO_FAIL(con.Query("CREATE TABLE fact(k BIGINT, v BIGINT)"));
    REQUIRE_NO_FAIL(con.Query("INSERT INTO fact SELECT (i % " + std::to_string(DOM) +
                              "), i FROM range(" + std::to_string(N) + ") t(i)"));
    REQUIRE_NO_FAIL(con.Query("CREATE TABLE dimB(k BIGINT)"));
    REQUIRE_NO_FAIL(con.Query("INSERT INTO dimB SELECT i FROM range(" + std::to_string(DOM) +
                              ") t(i)"));

    const string sql =
        "SELECT fact.k, fact.v, dimA.k AS ak, dimB.k AS bk "
        "FROM fact INNER JOIN dimA ON fact.k = dimA.k "
        "LEFT JOIN dimB ON fact.k = dimB.k";

    // Sanity: at full selectivity the plan must carry the separated SJ probe,
    // otherwise the sweep is measuring plain hash joins and is meaningless.
    REQUIRE_NO_FAIL(con.Query("CREATE TABLE dimA(k BIGINT)"));
    REQUIRE_NO_FAIL(con.Query("INSERT INTO dimA SELECT i FROM range(" + std::to_string(DOM) +
                              ") t(i)"));
    RequireSJProbe(con, sql, SJMode::BITMAP);

    std::printf("\nSelectivity sweep  (fact=%lld rows, key domain=%lld, join key=fact.k)\n",
                (long long)N, (long long)DOM);
    std::printf("%6s  %8s  %8s  %9s  %8s  %8s\n", "p", "Bmp(s)", "Hash(s)", "Base(s)", "SpBmp", "SpHash");
    std::printf("%6s  %8s  %8s  %9s  %8s  %8s\n", "------", "--------", "--------", "---------",
                "--------", "--------");
    for (int pct = 0; pct <= 100; pct += 10) {
        const int64_t keep = (DOM * pct) / 100;
        REQUIRE_NO_FAIL(con.Query("DROP TABLE dimA"));
        REQUIRE_NO_FAIL(con.Query("CREATE TABLE dimA(k BIGINT)"));
        if (keep > 0) {
            REQUIRE_NO_FAIL(con.Query("INSERT INTO dimA SELECT i FROM range(" +
                                      std::to_string(keep) + ") t(i)"));
        }
        Apply(con, SJMode::BITMAP);   double t_bmp  = TimeMin(con, sql, RUNS);
        Apply(con, SJMode::HASH);     double t_hash = TimeMin(con, sql, RUNS);
        Apply(con, SJMode::BASELINE); double t_base = TimeMin(con, sql, RUNS);
        std::printf("%5d%%  %8.4f  %8.4f  %9.4f  %7.2fx  %7.2fx\n", pct, t_bmp, t_hash, t_base,
                    t_base / t_bmp, t_base / t_hash);
    }
    std::printf("\nSpeedup = baseline / mode  (>1x = SJ faster). "
                "p = fraction of fact keys kept by the semi-join.\n\n");
}
