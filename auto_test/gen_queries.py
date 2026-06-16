#!/usr/bin/env python3
# ============================================================================
# gen_queries.py — the single OuterYan query-corpus generator
#
# One script, dispatched by a target argument, regenerates every family under
# outerjoin_query/. It supersedes the former per-corpus scripts
# (gen_equivalence_queries / gen_benchmark_queries / gen_predicate_queries /
# gen_tpc_predicate_queries / gen_semijoin_queries): all of them shared the same
# "variance shape" — topology families × join-type vectors
# {allINNER,allLEFT,allRIGHT,allFULL,mixA,mixB,mixC} — so KIND, vectors(),
# OFF_PREFIX and write_pair() live here once and only the join graph differs.
#
# Each ON/OFF query ships as a FILE PAIR in the compare_equal.sh convention:
#   <label>.sql       the bare query              -> OuterYan ON  (default)
#   <label>_off.sql   SET disabled_optimizers     -> OuterYan OFF (oracle)
#                     TO 'outer_yan'; <same query>
# TPC predicate variants and the semijoin corpus are bare-only: the bench /
# semijoin runners compare ON-vs-OFF in-engine, so no _off file is needed.
#
# USAGE: gen_queries.py [equiv|pred|tpch|tpcds|bench|semijoin|all]  (default all)
#   equiv     equivalence/select_star/  SELECT * structural matrix N=3..6 + chains
#             equivalence/aggregation/  COUNT/SUM … GROUP BY over R/S/T/K
#             equivalence/predicates/   shapes + WHERE value predicate (no NULL)
#   pred      equivalence/predicates/   (only)
#   tpch      tpch/   real TPC-H FK trees (SELECT*+agg) + <anchor>_p* value preds
#   tpcds     tpcds/  real TPC-DS FK trees (SELECT*+agg) + <anchor>_p* value preds
#   bench     = tpch + tpcds
#   semijoin  semijoin/  star-schema fact⋈dim corpus for experiment_semijoin.sh
#   all       = equiv + tpch + tpcds + semijoin
#
# Hand-written TPC anchors (th1..thN / ds1..dsN) are preserved; only the labels
# this script owns are (re)written. SELECT * over the real schemas is
# collision-free (every table uses a unique column prefix). All WHERE predicates
# are VALUE predicates — no NULL tests. Re-run to regenerate / extend.
# ============================================================================
import os
import re
import sys
import glob

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outerjoin_query")
EQUIV_BASE = os.path.join(BASE, "equivalence")
SELECT_DIR = os.path.join(EQUIV_BASE, "select_star")
AGG_DIR = os.path.join(EQUIV_BASE, "aggregation")
PRED_DIR = os.path.join(EQUIV_BASE, "predicates")
TPCH_DIR = os.path.join(BASE, "tpch")
TPCDS_DIR = os.path.join(BASE, "tpcds")
SEMI_DIR = os.path.join(BASE, "semijoin")

OFF_PREFIX = "SET disabled_optimizers TO 'outer_yan';\n"
KIND = {"INNER": "INNER JOIN", "LEFT": "LEFT OUTER JOIN",
        "RIGHT": "RIGHT OUTER JOIN", "FULL": "FULL OUTER JOIN"}


# --- shared core -------------------------------------------------------------
def vectors(e):
    """The 7 join-type kind vectors over e joins (cyclic mixes after position 3)."""
    cyc = lambda seq: [seq[i % 4] for i in range(e)]
    return {"allINNER": ["INNER"] * e, "allLEFT": ["LEFT"] * e,
            "allRIGHT": ["RIGHT"] * e, "allFULL": ["FULL"] * e,
            "mixA": cyc(["LEFT", "INNER", "RIGHT", "FULL"]),
            "mixB": cyc(["FULL", "RIGHT", "INNER", "LEFT"]),
            "mixC": cyc(["RIGHT", "FULL", "LEFT", "INNER"])}


def write_pair(outdir, label, sql):
    with open(os.path.join(outdir, f"{label}.sql"), "w") as f:
        f.write(sql + "\n")
    with open(os.path.join(outdir, f"{label}_off.sql"), "w") as f:
        f.write(OFF_PREFIX + sql + "\n")


def emit(outdir, queries):
    """Write all pairs into outdir (creating it); does NOT wipe pre-existing files."""
    os.makedirs(outdir, exist_ok=True)
    for label, sql in queries.items():
        write_pair(outdir, label, sql)
    return len(queries)


def wipe(outdir, keep=lambda f: False):
    """Remove every *.sql in outdir except those for which keep(filename) is True."""
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.endswith(".sql") and not keep(f):
            os.remove(os.path.join(outdir, f))


# ============================================================================
# Corpus 1 — equivalence: synthetic R1..R10 (dst=src) structural matrix
# ============================================================================
def lf(i): return {"sql": f"R{i}", "rels": [i]}
def jn(A, B, kind, a, b):
    return {"sql": f"({A['sql']} {KIND[kind]} {B['sql']} ON R{a}.dst=R{b}.src)",
            "rels": A["rels"] + B["rels"]}
def sel(t): return "SELECT * FROM " + t["sql"]


def shapes_for(n, k):
    S = {}
    t = lf(1)
    for i in range(2, n + 1): t = jn(t, lf(i), k[i - 2], i - 1, i)
    S["line"] = sel(t)
    t = lf(1)
    for i in range(2, n + 1): t = jn(t, lf(i), k[i - 2], 1, i)
    S["star"] = sel(t)
    if n == 3:
        S["bushyR"] = sel(jn(lf(1), jn(lf(2), lf(3), k[1], 2, 3), k[0], 1, 2))
    elif n == 4:
        S["bushyBal"]  = sel(jn(jn(lf(1), lf(2), k[0], 1, 2), jn(lf(3), lf(4), k[2], 3, 4), k[1], 2, 3))
        S["bushyBal2"] = sel(jn(jn(lf(1), lf(2), k[0], 1, 2), jn(lf(3), lf(4), k[2], 3, 4), k[1], 1, 3))
        S["branchY"]   = sel(jn(jn(lf(1), jn(lf(2), lf(3), k[1], 2, 3), k[0], 1, 2), lf(4), k[2], 2, 4))
    elif n == 5:
        S["bushyBal"] = sel(jn(jn(jn(lf(1), lf(2), k[0], 1, 2), lf(3), k[1], 2, 3),
                               jn(lf(4), lf(5), k[3], 4, 5), k[2], 3, 4))
        S["bushyR"]   = sel(jn(lf(1), jn(lf(2), jn(lf(3), jn(lf(4), lf(5), k[3], 4, 5), k[2], 3, 4),
                               k[1], 2, 3), k[0], 1, 2))
        S["branch"]   = sel(jn(jn(lf(1), lf(2), k[0], 1, 2),
                               jn(jn(lf(3), lf(4), k[2], 3, 4), lf(5), k[3], 3, 5), k[1], 2, 3))
    elif n == 6:
        S["bushyBal"] = sel(jn(jn(jn(lf(1), lf(2), k[0], 1, 2), lf(3), k[1], 2, 3),
                               jn(jn(lf(4), lf(5), k[3], 4, 5), lf(6), k[4], 5, 6), k[2], 3, 4))
        S["bushy2"]   = sel(jn(jn(lf(1), jn(lf(2), lf(3), k[1], 2, 3), k[0], 1, 2),
                               jn(lf(4), jn(lf(5), lf(6), k[4], 5, 6), k[3], 4, 5), k[2], 3, 4))
        S["branch"]   = sel(jn(jn(jn(lf(1), lf(2), k[0], 1, 2), jn(lf(3), lf(4), k[2], 3, 4), k[1], 2, 3),
                               jn(lf(5), lf(6), k[4], 5, 6), k[3], 2, 5))
    return S


def matrix_queries():
    out = {}
    for n in range(3, 7):
        vs = vectors(n - 1)
        for sname in shapes_for(n, vs["allINNER"]):
            for vname, k in vs.items():
                out[f"{sname}_N{n}_{vname}"] = shapes_for(n, k)[sname] + ";"
    return out


def extra_queries():
    q = {}
    q["agg_count_INNER_INNER_RIGHT"] = (
        "SELECT R.src AS v1, COUNT(*) AS cnt FROM R INNER JOIN S ON R.dst=S.src "
        "INNER JOIN T ON S.dst=T.src RIGHT OUTER JOIN K ON T.dst=K.src GROUP BY R.src;")
    q["agg_count_LEFT_LEFT_FULL"] = (
        "SELECT R.src AS v1, COUNT(*) AS cnt FROM R LEFT OUTER JOIN S ON R.dst=S.src "
        "LEFT OUTER JOIN T ON S.dst=T.src FULL OUTER JOIN K ON T.dst=K.src GROUP BY R.src;")
    q["agg_count_INNER_FULL_3rel"] = (
        "SELECT R.src AS v1, COUNT(*) AS cnt FROM R INNER JOIN S ON R.dst=S.src "
        "FULL OUTER JOIN T ON S.dst=T.src GROUP BY R.src;")
    q["agg_sum_INNER_INNER_RIGHT"] = (
        "SELECT R.src AS v1, sum(K.dst) AS total FROM R INNER JOIN S ON R.dst=S.src "
        "INNER JOIN T ON S.dst=T.src RIGHT OUTER JOIN K ON T.dst=K.src GROUP BY R.src;")
    q["agg_sum_LEFT_LEFT_FULL"] = (
        "SELECT R.src AS v1, sum(K.dst) AS total FROM R LEFT OUTER JOIN S ON R.dst=S.src "
        "LEFT OUTER JOIN T ON S.dst=T.src FULL OUTER JOIN K ON T.dst=K.src GROUP BY R.src;")
    q["chain_N7_LEFT_INNER_mix"] = (
        "SELECT * FROM R1 LEFT OUTER JOIN R2 ON R1.dst=R2.src INNER JOIN R3 ON R2.dst=R3.src "
        "LEFT OUTER JOIN R4 ON R3.dst=R4.src LEFT OUTER JOIN R5 ON R4.dst=R5.src "
        "INNER JOIN R6 ON R5.dst=R6.src LEFT OUTER JOIN R7 ON R6.dst=R7.src;")
    q["chain_N10_LEFT"] = (
        "SELECT * FROM R1 LEFT OUTER JOIN R2 ON R1.dst=R2.src LEFT OUTER JOIN R3 ON R2.dst=R3.src "
        "LEFT OUTER JOIN R4 ON R3.dst=R4.src LEFT OUTER JOIN R5 ON R4.dst=R5.src "
        "LEFT OUTER JOIN R6 ON R5.dst=R6.src LEFT OUTER JOIN R7 ON R6.dst=R7.src "
        "LEFT OUTER JOIN R8 ON R7.dst=R8.src LEFT OUTER JOIN R9 ON R8.dst=R9.src "
        "LEFT OUTER JOIN R10 ON R9.dst=R10.src;")
    return q


def gen_equiv():
    for d in (SELECT_DIR, AGG_DIR):
        wipe(d)
    sel_q = dict(matrix_queries())
    agg_q = {}
    for label, sql in extra_queries().items():
        (agg_q if label.startswith("agg_") else sel_q)[label] = sql
    for label, sql in sel_q.items():
        write_pair(SELECT_DIR, label, sql)
    for label, sql in agg_q.items():
        write_pair(AGG_DIR, label, sql)
    print(f"select_star/: {len(sel_q)} pairs ; aggregation/: {len(agg_q)} pairs "
          f"({2 * (len(sel_q) + len(agg_q))} files total)")


# ============================================================================
# Corpus 2 — equivalence predicates: the structural shapes WITH a WHERE filter,
# so semi-join reduction is exercised under predicates. VALUE predicates only
# (equality / range / modulo / BETWEEN / IN / compound AND-OR — no NULL tests),
# on R1/R2 which every base references. 54 pairs = 6 shapes × 9 predicates.
# ============================================================================
EQUIV_PREDS = {
    "gt":      "R1.src > 100",
    "ge":      "R2.src >= 100",
    "eq":      "R1.src = 210",
    "mod":     "R1.src % 2 = 0",
    "range":   "R1.dst < 5000000",
    "between": "R1.dst BETWEEN 0 AND 1000000",
    "inlist":  "R1.src IN (10, 210, 410, 610, 810)",
    "and":     "R1.src > 100 AND R2.dst < 5000000",
    "or":      "R1.src < 100 OR R2.dst > 5000000",
}


def pred_bases():
    """6 curated base join expressions (no SELECT/WHERE), all referencing R1 & R2."""
    return {
        "line_N3_allLEFT":     jn(jn(lf(1), lf(2), "LEFT", 1, 2), lf(3), "LEFT", 2, 3)["sql"],
        "line_N4_mixA":        jn(jn(jn(lf(1), lf(2), "LEFT", 1, 2), lf(3), "INNER", 2, 3), lf(4), "RIGHT", 3, 4)["sql"],
        "star_N3_allLEFT":     jn(jn(lf(1), lf(2), "LEFT", 1, 2), lf(3), "LEFT", 1, 3)["sql"],
        "star_N4_mixA":        jn(jn(jn(lf(1), lf(2), "LEFT", 1, 2), lf(3), "INNER", 1, 3), lf(4), "RIGHT", 1, 4)["sql"],
        "bushyR_N3_mixA":      jn(lf(1), jn(lf(2), lf(3), "INNER", 2, 3), "LEFT", 1, 2)["sql"],
        "bushyBal_N4_allLEFT": jn(jn(lf(1), lf(2), "LEFT", 1, 2), jn(lf(3), lf(4), "LEFT", 3, 4), "LEFT", 2, 3)["sql"],
    }


def gen_equiv_pred():
    wipe(PRED_DIR)
    n = 0
    for bname, expr in pred_bases().items():
        for pname, pred in EQUIV_PREDS.items():
            write_pair(PRED_DIR, f"{bname}_{pname}", f"SELECT * FROM {expr} WHERE {pred};")
            n += 1
    print(f"predicates/: {n} pairs")


# ============================================================================
# Corpus 3 — benchmark: real TPC-H / TPC-DS FK trees
#
# A topology is (label, njoins, body): body has slots {0}..{njoins-1} for the
# JOIN keyword in textual order and bakes in the real FK predicates. Each
# topology fans out into one query per join-type vector.
# ============================================================================
def expand(topologies):
    out = {}
    for label, nj, body in topologies:
        for vname, ks in vectors(nj).items():
            out[f"{label}_{vname}"] = "SELECT * FROM " + body.format(*[KIND[k] for k in ks]) + ";"
    return out


def agg_query(body, sel_clause, grp, ks):
    frm = body.format(*[KIND[k] for k in ks])
    tail = f" GROUP BY {grp}" if grp else ""
    return f"SELECT {sel_clause} FROM {frm}{tail};"


def build_agg(specs):
    return {label: agg_query(body, sc, grp, vectors(nj)[v])
            for (label, nj, body, sc, grp, v) in specs}


# --- TPC-H -------------------------------------------------------------------
# FK edges: r_regionkey=n_regionkey · n_nationkey=s_nationkey · n_nationkey=
# c_nationkey · s_suppkey=ps_suppkey · p_partkey=ps_partkey · c_custkey=
# o_custkey · o_orderkey=l_orderkey · p_partkey=l_partkey · s_suppkey=l_suppkey
TPCH_SHAPES = [
    ("thline_N3", 2,
     "((region {0} nation ON r_regionkey=n_regionkey) "
     "{1} supplier ON n_nationkey=s_nationkey)"),
    ("thline_N5", 4,
     "((((region {0} nation ON r_regionkey=n_regionkey) "
     "{1} customer ON n_nationkey=c_nationkey) "
     "{2} orders ON c_custkey=o_custkey) "
     "{3} lineitem ON o_orderkey=l_orderkey)"),
    ("thstar_N4", 3,
     "(((lineitem {0} orders ON l_orderkey=o_orderkey) "
     "{1} part ON l_partkey=p_partkey) "
     "{2} supplier ON l_suppkey=s_suppkey)"),
    ("thbushyR_N3", 2,
     "(region {0} (nation {1} supplier ON n_nationkey=s_nationkey) "
     "ON r_regionkey=n_regionkey)"),
    ("thbushyBal_N4", 3,
     "((orders {0} lineitem ON o_orderkey=l_orderkey) "
     "{1} (part {2} partsupp ON p_partkey=ps_partkey) ON l_partkey=p_partkey)"),
    ("thbranch_N5", 4,
     "((customer {0} orders ON c_custkey=o_custkey) "
     "{1} ((region {2} nation ON r_regionkey=n_regionkey) "
     "{3} supplier ON n_nationkey=s_nationkey) ON c_nationkey=n_nationkey)"),
]

# Deep flat chains (kinds hand-chosen, like equivalence chain_N7/N10; RIGHT/FULL
# in an unparenthesized chain is intentionally avoided).
TPCH_CHAINS = {
    "thchain_N5_LEFT":
        "SELECT * FROM customer LEFT OUTER JOIN orders ON c_custkey=o_custkey "
        "LEFT OUTER JOIN lineitem ON o_orderkey=l_orderkey "
        "LEFT OUTER JOIN supplier ON l_suppkey=s_suppkey "
        "LEFT OUTER JOIN nation ON s_nationkey=n_nationkey;",
    "thchain_N5_LEFT_INNER_mix":
        "SELECT * FROM customer LEFT OUTER JOIN orders ON c_custkey=o_custkey "
        "INNER JOIN lineitem ON o_orderkey=l_orderkey "
        "LEFT OUTER JOIN supplier ON l_suppkey=s_suppkey "
        "INNER JOIN nation ON s_nationkey=n_nationkey;",
}

TPCH_AGG_A = ("((customer {0} orders ON c_custkey=o_custkey) "
              "{1} lineitem ON o_orderkey=l_orderkey)")
TPCH_AGG_B = ("(((region {0} nation ON r_regionkey=n_regionkey) "
              "{1} supplier ON n_nationkey=s_nationkey) "
              "{2} customer ON s_nationkey=c_nationkey)")
TPCH_AGG = [
    ("thagg_count_lineitem",     2, TPCH_AGG_A,
     "c_mktsegment, COUNT(*) AS cnt", "c_mktsegment", "allLEFT"),
    ("thagg_sum_revenue",        2, TPCH_AGG_A,
     "c_mktsegment, SUM(l_extendedprice) AS revenue", "c_mktsegment", "allFULL"),
    ("thagg_avg_qty",            2, TPCH_AGG_A,
     "c_mktsegment, AVG(l_quantity) AS avg_qty", "c_mktsegment", "mixA"),
    ("thagg_countdistinct_ord",  2, TPCH_AGG_A,
     "c_mktsegment, COUNT(DISTINCT o_orderkey) AS n_orders", "c_mktsegment", "allRIGHT"),
    ("thagg_count_by_region",    3, TPCH_AGG_B,
     "r_name, COUNT(*) AS cnt", "r_name", "allFULL"),
    ("thagg_minmax_bal",         3, TPCH_AGG_B,
     "r_name, MIN(s_acctbal) AS min_bal, MAX(c_acctbal) AS max_bal", "r_name", "allLEFT"),
    ("thagg_multi_by_nation",    3, TPCH_AGG_B,
     "n_name, COUNT(*) AS cnt, SUM(s_acctbal) AS tot_bal", "n_name", "mixB"),
    ("thagg_global",             3, TPCH_AGG_B,
     "COUNT(*) AS cnt, SUM(c_acctbal) AS tot_bal", "", "allLEFT"),
]


# --- TPC-DS ------------------------------------------------------------------
# FK edges: ss_item_sk=i_item_sk · ss_customer_sk=c_customer_sk · ss_store_sk=
# s_store_sk · ss_addr_sk=ca_address_sk · ss_promo_sk=p_promo_sk · c_current_
# addr_sk=ca_address_sk · c_current_cdemo_sk=cd_demo_sk · ws_bill_customer_sk=
# c_customer_sk · ws_item_sk=i_item_sk
TPCDS_SHAPES = [
    ("dsline_N3", 2,
     "((store_sales {0} customer ON ss_customer_sk=c_customer_sk) "
     "{1} customer_address ON c_current_addr_sk=ca_address_sk)"),
    ("dsline_N4", 3,
     "(((store_sales {0} customer ON ss_customer_sk=c_customer_sk) "
     "{1} customer_address ON c_current_addr_sk=ca_address_sk) "
     "{2} customer_demographics ON c_current_cdemo_sk=cd_demo_sk)"),
    ("dsstar_N4", 3,
     "(((store_sales {0} item ON ss_item_sk=i_item_sk) "
     "{1} customer ON ss_customer_sk=c_customer_sk) "
     "{2} store ON ss_store_sk=s_store_sk)"),
    ("dsstar_N6", 5,
     "(((((store_sales {0} item ON ss_item_sk=i_item_sk) "
     "{1} customer ON ss_customer_sk=c_customer_sk) "
     "{2} store ON ss_store_sk=s_store_sk) "
     "{3} customer_address ON ss_addr_sk=ca_address_sk) "
     "{4} promotion ON ss_promo_sk=p_promo_sk)"),
    ("dswebstar_N3", 2,
     "((web_sales {0} customer ON ws_bill_customer_sk=c_customer_sk) "
     "{1} item ON ws_item_sk=i_item_sk)"),
    ("dsbushyR_N3", 2,
     "(store_sales {0} (customer {1} customer_address "
     "ON c_current_addr_sk=ca_address_sk) ON ss_customer_sk=c_customer_sk)"),
    ("dsbushyBal_N4", 3,
     "((store_sales {0} item ON ss_item_sk=i_item_sk) "
     "{1} (customer {2} customer_address ON c_current_addr_sk=ca_address_sk) "
     "ON ss_customer_sk=c_customer_sk)"),
    ("dsbranch_N5", 4,
     "((store_sales {0} item ON ss_item_sk=i_item_sk) "
     "{1} ((customer {2} customer_address ON c_current_addr_sk=ca_address_sk) "
     "{3} customer_demographics ON c_current_cdemo_sk=cd_demo_sk) "
     "ON ss_customer_sk=c_customer_sk)"),
]

TPCDS_CHAINS = {
    "dschain_N4_LEFT":
        "SELECT * FROM store_sales "
        "LEFT OUTER JOIN customer ON ss_customer_sk=c_customer_sk "
        "LEFT OUTER JOIN customer_address ON c_current_addr_sk=ca_address_sk "
        "LEFT OUTER JOIN customer_demographics ON c_current_cdemo_sk=cd_demo_sk;",
    "dschain_N4_LEFT_INNER_mix":
        "SELECT * FROM store_sales "
        "LEFT OUTER JOIN customer ON ss_customer_sk=c_customer_sk "
        "INNER JOIN customer_address ON c_current_addr_sk=ca_address_sk "
        "LEFT OUTER JOIN customer_demographics ON c_current_cdemo_sk=cd_demo_sk;",
}

TPCDS_AGG_A = ("((store_sales {0} customer ON ss_customer_sk=c_customer_sk) "
               "{1} customer_address ON c_current_addr_sk=ca_address_sk)")
TPCDS_AGG_B = ("((store_sales {0} item ON ss_item_sk=i_item_sk) "
               "{1} store ON ss_store_sk=s_store_sk)")
TPCDS_AGG = [
    ("dsagg_count_by_state",     2, TPCDS_AGG_A,
     "ca_state, COUNT(*) AS cnt", "ca_state", "allLEFT"),
    ("dsagg_sum_profit",         2, TPCDS_AGG_A,
     "ca_state, SUM(ss_net_profit) AS profit", "ca_state", "allFULL"),
    ("dsagg_avg_price",          2, TPCDS_AGG_A,
     "ca_state, AVG(ss_sales_price) AS avg_price", "ca_state", "mixA"),
    ("dsagg_countdistinct_cust", 2, TPCDS_AGG_A,
     "ca_state, COUNT(DISTINCT ss_customer_sk) AS n_cust", "ca_state", "allRIGHT"),
    ("dsagg_count_by_category",  2, TPCDS_AGG_B,
     "i_category, COUNT(*) AS cnt", "i_category", "allFULL"),
    ("dsagg_minmax_price",       2, TPCDS_AGG_B,
     "i_category, MIN(ss_sales_price) AS lo, MAX(ss_sales_price) AS hi", "i_category", "allLEFT"),
    ("dsagg_multi_by_store",     2, TPCDS_AGG_B,
     "s_state, COUNT(*) AS cnt, SUM(ss_quantity) AS qty", "s_state", "mixB"),
    ("dsagg_global",             2, TPCDS_AGG_B,
     "COUNT(*) AS cnt, SUM(ss_net_profit) AS profit", "", "allLEFT"),
]


# --- TPC predicate variants --------------------------------------------------
# Append a VALUE WHERE predicate to each hand-written named anchor (th1.. / ds1..)
# on a numeric column of the query's leading table. Bare-only (the bench suite
# compares ON-vs-OFF in-engine). Small constants + modulo so the predicate
# selects a fraction for any key range (incl. tiny dims like region 0..4).
TPC_COLS = {
    "tpch": {"customer": "c_custkey", "orders": "o_orderkey", "lineitem": "l_orderkey",
             "nation": "n_nationkey", "supplier": "s_suppkey", "region": "r_regionkey",
             "part": "p_partkey", "partsupp": "ps_partkey"},
    "tpcds": {"customer": "c_customer_sk", "store_sales": "ss_item_sk", "web_sales": "ws_item_sk",
              "item": "i_item_sk", "store": "s_store_sk", "customer_address": "ca_address_sk",
              "date_dim": "d_date_sk", "catalog_sales": "cs_item_sk"},
}
TPC_DIR = {"tpch": TPCH_DIR, "tpcds": TPCDS_DIR}
TPC_ANCHOR = {"tpch": "th", "tpcds": "ds"}  # named-anchor filename prefix (th1_, ds1_, …)


def tpc_preds(c):  # value predicates (no NULL) on column c
    return {
        "gt2":   f"{c} > 2",
        "mod2":  f"{c} % 2 = 0",
        "mod3":  f"{c} % 3 = 1",
        "ge1":   f"{c} >= 1",
        "lt":    f"{c} < 1000000",
        "bet":   f"{c} BETWEEN 1 AND 1000",
        "inlist":f"{c} IN (1, 2, 3, 5, 8, 13)",
        "and":   f"{c} > 1 AND {c} % 2 = 0",
        "or":    f"{c} < 5 OR {c} % 2 = 0",
    }


# A predicate variant ends in _p<key> for exactly these keys — pin the match to
# them so it never collides with base names that merely contain "_p…" (e.g.
# dsagg_avg_price, dsagg_sum_profit).
PRED_VARIANT_RE = re.compile(r"_p(" + "|".join(tpc_preds("x")) + r")\.sql$")


def gen_tpc_pred(fam):
    d = TPC_DIR[fam]
    wipe(d, keep=lambda f: not PRED_VARIANT_RE.search(f))  # only re-wipe _p<key> variants
    n = 0
    for base in sorted(glob.glob(os.path.join(d, f"{TPC_ANCHOR[fam]}[0-9]_*.sql"))):
        b = os.path.basename(base)
        if b.endswith("_off.sql") or PRED_VARIANT_RE.search(b):
            continue
        sql = open(base).read().strip().rstrip(";").strip()
        m = re.search(r"\bFROM\s+([a-z_]+)", sql, re.I)
        col = TPC_COLS[fam].get(m.group(1).lower()) if m else None
        if not col:
            continue
        label = b[:-4]  # strip .sql
        for pn, pred in tpc_preds(col).items():
            with open(os.path.join(d, f"{label}_p{pn}.sql"), "w") as fh:
                fh.write(f"{sql} WHERE {pred};\n")
            n += 1
    print(f"{fam}/: {n} predicate variants (_p*; {TPC_ANCHOR[fam]}1.. anchors preserved)")


def gen_tpch():
    q = {}
    q.update(expand(TPCH_SHAPES))
    q.update(TPCH_CHAINS)
    q.update(build_agg(TPCH_AGG))
    n = emit(TPCH_DIR, q)
    print(f"tpch/: {n} generated pairs (th1..th5 anchors preserved)")
    gen_tpc_pred("tpch")


def gen_tpcds():
    q = {}
    q.update(expand(TPCDS_SHAPES))
    q.update(TPCDS_CHAINS)
    q.update(build_agg(TPCDS_AGG))
    n = emit(TPCDS_DIR, q)
    print(f"tpcds/: {n} generated pairs (ds1..ds5 anchors preserved)")
    gen_tpc_pred("tpcds")


# ============================================================================
# Corpus 4 — semijoin: SELECT * over a star schema (fact + d1/d2/d3) where a
# small dimension reduces the large fact through the join, so OuterYan can insert
# a semi-join / bloom filter. Bare-only; experiment_semijoin.sh runs each ON/OFF.
# ~54 acyclic, reduction-amenable shapes × join-type vectors:
#   single  d_j ⋈ fact (3 FKs × 4 join types)   star2  fact ⋈ d_a ⋈ d_b
#   star3   fact ⋈ d1 ⋈ d2 ⋈ d3                  chain  d_a ⋈ fact ⋈ d_b
# skeleton_*.sql (the selectivity-sweep template) is hand-kept and preserved.
# ============================================================================
def gen_semijoin():
    wipe(SEMI_DIR, keep=lambda f: f.startswith("skeleton_"))
    Q = {}
    for j in (1, 2, 3):                                   # single: d_j ⋈ fact
        for kt in ("INNER", "LEFT", "RIGHT", "FULL"):
            Q[f"single_fk{j}_{kt}"] = f"SELECT * FROM d{j} {KIND[kt]} fact ON d{j}.k=fact.fk{j}"
    for a, b in ((1, 2), (1, 3), (2, 3)):                 # star2: fact ⋈ d_a ⋈ d_b
        for vn, k in vectors(2).items():
            Q[f"star2_fk{a}{b}_{vn}"] = (
                f"SELECT * FROM (fact {KIND[k[0]]} d{a} ON fact.fk{a}=d{a}.k) "
                f"{KIND[k[1]]} d{b} ON fact.fk{b}=d{b}.k")
    for vn, k in vectors(3).items():                      # star3: fact ⋈ d1 ⋈ d2 ⋈ d3
        Q[f"star3_{vn}"] = (
            f"SELECT * FROM ((fact {KIND[k[0]]} d1 ON fact.fk1=d1.k) "
            f"{KIND[k[1]]} d2 ON fact.fk2=d2.k) {KIND[k[2]]} d3 ON fact.fk3=d3.k")
    for a, b, tag in ((1, 2, "fk12"), (1, 3, "fk13")):    # chain: d_a ⋈ fact ⋈ d_b
        for vn, k in vectors(2).items():
            Q[f"chain_{tag}_{vn}"] = (
                f"SELECT * FROM (d{a} {KIND[k[0]]} fact ON d{a}.k=fact.fk{a}) "
                f"{KIND[k[1]]} d{b} ON fact.fk{b}=d{b}.k")
    for label, sql in Q.items():
        with open(os.path.join(SEMI_DIR, f"{label}.sql"), "w") as fh:
            fh.write(sql + ";\n")
    print(f"semijoin/: {len(Q)} queries")


# --- dispatch ----------------------------------------------------------------
TARGETS = {
    "equiv":    [gen_equiv, gen_equiv_pred],
    "pred":     [gen_equiv_pred],
    "tpch":     [gen_tpch],
    "tpcds":    [gen_tpcds],
    "bench":    [gen_tpch, gen_tpcds],
    "semijoin": [gen_semijoin],
    "all":      [gen_equiv, gen_equiv_pred, gen_tpch, gen_tpcds, gen_semijoin],
}


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target not in TARGETS:
        sys.exit(f"Usage: {os.path.basename(sys.argv[0])} "
                 f"[{'|'.join(TARGETS)}]   (default: all)")
    for fn in TARGETS[target]:
        fn()


if __name__ == "__main__":
    main()
