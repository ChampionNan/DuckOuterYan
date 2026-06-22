#!/usr/bin/env python3
# ============================================================================
# gen_queries.py — the single OuterYan query-corpus generator
#
# One script, dispatched by a target argument, regenerates every family under
# outerjoin_query/. It consolidates all query generation:
#   - graph/       predicate-bearing structural queries on R1..R10
#   - tpch/        diverse topologies on TPC-H schema
#   - tpcds/       diverse topologies on TPC-DS schema
#   - job/         diverse topologies on JOB/IMDb schema
#
# USAGE: gen_queries.py [graph|pred|tpch|tpcds|job|bench|validate|all]  (default all)
#   graph     graph/    predicates on graph R1..R10 tables
#   pred      graph/    (alias for graph)
#   tpch      tpch/     diverse topologies on TPC-H schema
#   tpcds     tpcds/    diverse topologies on TPC-DS schema
#   job       job/      diverse topologies on JOB/IMDb schema
#   bench     = tpch + tpcds + job
#   validate  EXPLAIN-check all queries against DBs, remove broken ones
#   all       = graph + bench
# ============================================================================
import os
import sys
import glob
import random
import re

random.seed(42)

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outerjoin_query")
GRAPH_BASE = os.path.join(BASE, "graph")
PRED_DIR = GRAPH_BASE  # flat directory, no subdirs
TPCH_DIR = os.path.join(BASE, "tpch")
TPCDS_DIR = os.path.join(BASE, "tpcds")
JOB_DIR = os.path.join(BASE, "job")

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
# Corpus 1 — graph: R1..R10 (dst=src) structural matrix
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


def gen_graph():
    """Generate graph predicate queries (flat in graph/)."""
    gen_graph_pred()


# ============================================================================
# Corpus 2 — graph selectivity: structural shapes with modulo-based WHERE
# predicates controlling selectivity from 1% to 95%.
# 6 shapes x 9 selectivities = 54 pairs.
# ============================================================================
GRAPH_PREDS = {
    "s01":  "R1.src % 100 = 0",       #  ~1% selectivity
    "s05":  "R1.src % 20 = 0",        #  ~5% selectivity
    "s10":  "R1.src % 10 = 0",        # ~10% selectivity
    "s20":  "R1.src % 5 = 0",         # ~20% selectivity
    "s33":  "R1.src % 3 = 0",         # ~33% selectivity
    "s50":  "R1.src % 2 = 0",         # ~50% selectivity
    "s67":  "R1.src % 3 <> 0",        # ~67% selectivity
    "s80":  "R1.src % 5 <> 0",        # ~80% selectivity
    "s95":  "R1.src % 20 <> 0",       # ~95% selectivity
}


def pred_bases():
    """6 curated base join expressions (no SELECT/WHERE), all referencing R1 & R2.
    All use mixed join types (no all-same-direction)."""
    return {
        "line_N3_mixB":        jn(jn(lf(1), lf(2), "FULL", 1, 2), lf(3), "RIGHT", 2, 3)["sql"],
        "line_N4_mixA":        jn(jn(jn(lf(1), lf(2), "LEFT", 1, 2), lf(3), "INNER", 2, 3), lf(4), "RIGHT", 3, 4)["sql"],
        "star_N3_mixC":        jn(jn(lf(1), lf(2), "RIGHT", 1, 2), lf(3), "FULL", 1, 3)["sql"],
        "star_N4_mixA":        jn(jn(jn(lf(1), lf(2), "LEFT", 1, 2), lf(3), "INNER", 1, 3), lf(4), "RIGHT", 1, 4)["sql"],
        "bushyR_N3_mixA":      jn(lf(1), jn(lf(2), lf(3), "INNER", 2, 3), "LEFT", 1, 2)["sql"],
        "bushyBal_N4_mixB":    jn(jn(lf(1), lf(2), "FULL", 1, 2), jn(lf(3), lf(4), "RIGHT", 3, 4), "LEFT", 2, 3)["sql"],
    }


def gen_graph_pred():
    wipe(PRED_DIR)
    n = 0
    for bname, expr in pred_bases().items():
        for pname, pred in GRAPH_PREDS.items():
            write_pair(PRED_DIR, f"{bname}_{pname}", f"SELECT * FROM {expr} WHERE {pred};")
            n += 1
    print(f"graph/: {n} pairs")


# ============================================================================
# Bench queries — diverse topologies on TPC-H / TPC-DS / JOB schemas
# (formerly in _sqlstorm_v2.py)
# ============================================================================

# --- Join type vectors for bench queries (diverse mixes, >= 2 outer joins) ---
def bench_vectors(n_joins):
    """Generate diverse join-type vectors of length n_joins, each with >= 2 outer joins."""
    base_mixes = [
        # Heavy outer mixes
        ["LEFT", "RIGHT", "FULL", "LEFT", "RIGHT", "FULL", "LEFT", "RIGHT",
         "FULL", "LEFT", "RIGHT", "FULL", "LEFT", "RIGHT", "FULL"],
        ["RIGHT", "FULL", "LEFT", "RIGHT", "FULL", "LEFT", "RIGHT", "FULL",
         "LEFT", "RIGHT", "FULL", "LEFT", "RIGHT", "FULL", "LEFT"],
        ["FULL", "LEFT", "RIGHT", "FULL", "LEFT", "RIGHT", "FULL", "LEFT",
         "RIGHT", "FULL", "LEFT", "RIGHT", "FULL", "LEFT", "RIGHT"],
        # Mixed with INNER
        ["LEFT", "INNER", "RIGHT", "FULL", "LEFT", "INNER", "RIGHT", "FULL",
         "LEFT", "INNER", "RIGHT", "FULL", "LEFT", "INNER", "RIGHT"],
        ["RIGHT", "INNER", "FULL", "LEFT", "RIGHT", "INNER", "FULL", "LEFT",
         "RIGHT", "INNER", "FULL", "LEFT", "RIGHT", "INNER", "FULL"],
        ["FULL", "INNER", "LEFT", "INNER", "RIGHT", "FULL", "INNER", "LEFT",
         "INNER", "RIGHT", "FULL", "INNER", "LEFT", "INNER", "RIGHT"],
        ["INNER", "LEFT", "FULL", "RIGHT", "INNER", "LEFT", "FULL", "RIGHT",
         "INNER", "LEFT", "FULL", "RIGHT", "INNER", "LEFT", "FULL"],
        # RIGHT-heavy
        ["RIGHT", "RIGHT", "LEFT", "RIGHT", "FULL", "RIGHT", "RIGHT", "LEFT",
         "RIGHT", "FULL", "RIGHT", "RIGHT", "LEFT", "RIGHT", "FULL"],
        # FULL-heavy
        ["FULL", "FULL", "LEFT", "FULL", "RIGHT", "FULL", "FULL", "LEFT",
         "FULL", "RIGHT", "FULL", "FULL", "LEFT", "FULL", "RIGHT"],
        # Alternating pairs
        ["LEFT", "RIGHT", "LEFT", "RIGHT", "LEFT", "RIGHT", "LEFT", "RIGHT",
         "LEFT", "RIGHT", "LEFT", "RIGHT", "LEFT", "RIGHT", "LEFT"],
        ["RIGHT", "LEFT", "RIGHT", "LEFT", "RIGHT", "LEFT", "RIGHT", "LEFT",
         "RIGHT", "LEFT", "RIGHT", "LEFT", "RIGHT", "LEFT", "RIGHT"],
        ["FULL", "RIGHT", "FULL", "LEFT", "FULL", "RIGHT", "FULL", "LEFT",
         "FULL", "RIGHT", "FULL", "LEFT", "FULL", "RIGHT", "FULL"],
    ]
    vecs = []
    for mix in base_mixes:
        v = mix[:n_joins]
        outer_count = sum(1 for k in v if k != "INNER")
        if outer_count >= 2:
            vecs.append(v)
    if not vecs:
        vecs.append(["LEFT", "RIGHT"] + ["INNER"] * (n_joins - 2))
    return vecs


# --- Predicates for bench queries ---
def _bench_predicates(col):
    """Return a list of simple predicates for a given column name."""
    return [
        f"{col} > 100",
        f"{col} < 50000",
        f"{col} >= 10",
        f"{col} <= 1000",
        f"{col} BETWEEN 50 AND 5000",
        f"{col} IN (1, 5, 10, 50, 100, 500)",
        f"{col} % 3 = 0",
        f"{col} % 7 <> 0",
        f"{col} > 0 AND {col} < 10000",
        f"{col} BETWEEN 1 AND 100",
        f"{col} IN (2, 4, 6, 8, 10, 12, 14)",
        f"{col} > 500",
        f"{col} % 2 = 1",
        f"{col} >= 100 AND {col} <= 9000",
        f"{col} < 200",
    ]


def _pick_pred(col, idx):
    """Deterministically pick a predicate for column using index."""
    preds = _bench_predicates(col)
    return preds[idx % len(preds)]


# --- Bench query builders ---
def _build_line_query(tables, join_conds, join_types, pred_col, pred_idx,
                      select_cols="*", agg=None, aliases=None):
    """Build a left-deep (line) query."""
    n = len(tables)
    assert len(join_conds) == n - 1
    assert len(join_types) == n - 1

    if aliases:
        from_clause = f"{tables[0]} {aliases[tables[0]]}"
    else:
        from_clause = tables[0]

    for i in range(1, n):
        jt = KIND[join_types[i-1]]
        if aliases:
            tbl = f"{tables[i]} {aliases[tables[i]]}"
        else:
            tbl = tables[i]
        from_clause += f"\n    {jt} {tbl} ON {join_conds[i-1]}"

    pred = _pick_pred(pred_col, pred_idx)

    if agg:
        sel_str = agg["select"]
        grp = agg.get("group_by", "")
        sql = f"SELECT {sel_str}\nFROM {from_clause}\nWHERE {pred}"
        if grp:
            sql += f"\nGROUP BY {grp}"
    else:
        sql = f"SELECT {select_cols}\nFROM {from_clause}\nWHERE {pred}"

    return sql + ";"


def _build_bushy_query(template, join_types, pred_col, pred_idx, select_cols="*"):
    """Build a bushy query from a template with {0},{1},... slots."""
    body = template.replace("{L}", "")
    for i, jt in enumerate(join_types):
        body = body.replace(f"{{{i}}}", KIND[jt])

    pred = _pick_pred(pred_col, pred_idx)
    sql = f"SELECT {select_cols}\nFROM {body}\nWHERE {pred};"
    return sql


def _build_right_deep_query(tables, join_conds, join_types, pred_col, pred_idx,
                            select_cols="*", aliases=None):
    """Build a right-deep tree: t0 J (t1 J (t2 J (t3 J t4)))."""
    n = len(tables)
    assert len(join_conds) == n - 1
    assert len(join_types) == n - 1

    def tbl_ref(i):
        if aliases:
            return f"{tables[i]} {aliases[tables[i]]}"
        return tables[i]

    inner = tbl_ref(n - 1)
    for i in range(n - 2, 0, -1):
        jt = KIND[join_types[i]]
        inner = f"({tbl_ref(i)} {jt} {inner} ON {join_conds[i]})"

    jt = KIND[join_types[0]]
    from_clause = f"{tbl_ref(0)} {jt} {inner} ON {join_conds[0]}"

    pred = _pick_pred(pred_col, pred_idx)
    sql = f"SELECT {select_cols}\nFROM {from_clause}\nWHERE {pred};"
    return sql


# ============================================================================
# TPC-H SCHEMA
# ============================================================================
TPCH_PRED_COLS = [
    "r_regionkey", "n_nationkey", "s_suppkey", "s_acctbal",
    "c_custkey", "c_acctbal", "p_partkey", "p_size", "p_retailprice",
    "ps_availqty", "ps_supplycost", "o_orderkey", "o_totalprice",
    "l_orderkey", "l_quantity", "l_extendedprice", "l_discount", "l_linenumber",
]

# Map each TPC-H table to its column-name prefix. Prefixes are underscore-
# anchored, so "p_" (part) and "ps_" (partsupp) never collide.
TPCH_TABLE_PREFIX = {
    "region": "r_", "nation": "n_", "supplier": "s_", "customer": "c_",
    "part": "p_", "partsupp": "ps_", "orders": "o_", "lineitem": "l_",
}
TPCH_ALL_TABLES = list(TPCH_TABLE_PREFIX)


def _tpch_col_table(col):
    """Return the table a TPC-H column belongs to (longest matching prefix)."""
    best = None
    for tbl, pre in TPCH_TABLE_PREFIX.items():
        if col.startswith(pre) and (best is None or
                                    len(pre) > len(TPCH_TABLE_PREFIX[best])):
            best = tbl
    return best


def _tpch_tables_in(text):
    """Set of TPC-H tables named in a FROM-clause fragment / bushy template."""
    low = text.lower()
    return {t for t in TPCH_ALL_TABLES if re.search(r"\b" + t + r"\b", low)}


def _tpch_pick_pred_col(tables, idx):
    """Deterministically pick a predicate column whose table is in `tables`.

    TPCH_PRED_COLS spans the whole schema, but each topology only joins a
    subset of tables. Restricting candidates to in-scope tables is what keeps
    the generated WHERE predicate bindable (otherwise e.g. a branch topology
    on customer/orders/region/nation/supplier could draw `p_size` from `part`,
    which isn't in the FROM clause -> Binder Error).
    """
    tabs = set(tables)
    allowed = [c for c in TPCH_PRED_COLS if _tpch_col_table(c) in tabs]
    return allowed[idx % len(allowed)]


def _tpch_line_topologies():
    """Line/chain topologies of various lengths."""
    topos = []
    topos.append(("th_line3a", ["region", "nation", "supplier"],
                  ["r_regionkey = n_regionkey", "n_nationkey = s_nationkey"], "line"))
    topos.append(("th_line3b", ["customer", "orders", "lineitem"],
                  ["c_custkey = o_custkey", "o_orderkey = l_orderkey"], "line"))
    topos.append(("th_line4a", ["region", "nation", "supplier", "partsupp"],
                  ["r_regionkey = n_regionkey", "n_nationkey = s_nationkey",
                   "s_suppkey = ps_suppkey"], "line"))
    topos.append(("th_line4b", ["region", "nation", "customer", "orders"],
                  ["r_regionkey = n_regionkey", "n_nationkey = c_nationkey",
                   "c_custkey = o_custkey"], "line"))
    topos.append(("th_line5", ["region", "nation", "customer", "orders", "lineitem"],
                  ["r_regionkey = n_regionkey", "n_nationkey = c_nationkey",
                   "c_custkey = o_custkey", "o_orderkey = l_orderkey"], "line"))
    topos.append(("th_line6", ["region", "nation", "supplier", "partsupp", "part", "lineitem"],
                  ["r_regionkey = n_regionkey", "n_nationkey = s_nationkey",
                   "s_suppkey = ps_suppkey", "ps_partkey = p_partkey",
                   "p_partkey = l_partkey"], "line"))
    topos.append(("th_line7", ["region", "nation", "customer", "orders", "lineitem", "supplier", "partsupp"],
                  ["r_regionkey = n_regionkey", "n_nationkey = c_nationkey",
                   "c_custkey = o_custkey", "o_orderkey = l_orderkey",
                   "l_suppkey = s_suppkey", "s_suppkey = ps_suppkey"], "line"))
    topos.append(("th_line8", ["region", "nation", "customer", "orders", "lineitem", "part", "supplier", "partsupp"],
                  ["r_regionkey = n_regionkey", "n_nationkey = c_nationkey",
                   "c_custkey = o_custkey", "o_orderkey = l_orderkey",
                   "l_partkey = p_partkey", "l_suppkey = s_suppkey",
                   "s_suppkey = ps_suppkey"], "line"))
    return topos


def _tpch_star_topologies():
    """Star topologies centered on lineitem or partsupp."""
    topos = []
    topos.append(("th_star4a", ["lineitem", "orders", "part", "supplier"],
                  ["l_orderkey = o_orderkey", "l_partkey = p_partkey",
                   "l_suppkey = s_suppkey"], "star"))
    topos.append(("th_star4b", ["partsupp", "part", "supplier", "lineitem"],
                  ["ps_partkey = p_partkey", "ps_suppkey = s_suppkey",
                   "ps_partkey = l_partkey"], "star"))
    topos.append(("th_star5", ["lineitem", "orders", "part", "supplier", "nation"],
                  ["l_orderkey = o_orderkey", "l_partkey = p_partkey",
                   "l_suppkey = s_suppkey", "s_nationkey = n_nationkey"], "star"))
    return topos


def _tpch_bushy_topologies():
    """Bushy (balanced) topologies."""
    topos = []
    topos.append(("th_bushy4a", "bushy",
                  "(({L} orders {0} lineitem ON o_orderkey = l_orderkey) "
                  "{1} ({L} part {2} partsupp ON p_partkey = ps_partkey) "
                  "ON l_partkey = p_partkey)", 3))
    topos.append(("th_bushy4b", "bushy",
                  "(({L} region {0} nation ON r_regionkey = n_regionkey) "
                  "{1} ({L} supplier {2} partsupp ON s_suppkey = ps_suppkey) "
                  "ON n_nationkey = s_nationkey)", 3))
    topos.append(("th_bushy5", "bushy",
                  "(({L} customer {0} orders ON c_custkey = o_custkey) "
                  "{1} (({L} part {2} supplier ON 1=1) "
                  "{3} lineitem ON p_partkey = l_partkey AND s_suppkey = l_suppkey) "
                  "ON o_orderkey = l_orderkey)", 4))
    topos.append(("th_bushy6", "bushy",
                  "((({L} region {0} nation ON r_regionkey = n_regionkey) "
                  "{1} customer ON n_nationkey = c_nationkey) "
                  "{2} (({L} orders {3} lineitem ON o_orderkey = l_orderkey) "
                  "{4} part ON l_partkey = p_partkey) "
                  "ON c_custkey = o_custkey)", 5))
    return topos


def _tpch_branch_topologies():
    """Branch/Y topologies."""
    topos = []
    topos.append(("th_branch5a", "bushy",
                  "(({L} customer {0} orders ON c_custkey = o_custkey) "
                  "{1} (({L} region {2} nation ON r_regionkey = n_regionkey) "
                  "{3} supplier ON n_nationkey = s_nationkey) "
                  "ON c_nationkey = n_nationkey)", 4))
    topos.append(("th_branch5b", "bushy",
                  "(({L} lineitem {0} part ON l_partkey = p_partkey) "
                  "{1} (({L} nation {2} region ON n_regionkey = r_regionkey) "
                  "{3} supplier ON n_nationkey = s_nationkey) "
                  "ON l_suppkey = s_suppkey)", 4))
    return topos


def gen_tpch_queries():
    """Generate ~100 diverse TPC-H queries."""
    queries = {}
    idx = 0

    # Line topologies (left-deep)
    line_topos = _tpch_line_topologies()
    for topo_label, tables, conds, shape in line_topos:
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[:5]):
            pred_col = _tpch_pick_pred_col(tables, idx + vi)
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_line_query(tables, conds, vec, pred_col, idx + vi)
            idx += 1

    # Right-deep versions of some line topologies
    for topo_label, tables, conds, shape in line_topos[:6]:
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[3:6]):
            pred_col = _tpch_pick_pred_col(tables, idx + vi)
            label = f"{topo_label}_rd_v{vi}"
            queries[label] = _build_right_deep_query(tables, conds, vec, pred_col, idx + vi)
            idx += 1

    # Star topologies
    star_topos = _tpch_star_topologies()
    for topo_label, tables, conds, shape in star_topos:
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[:5]):
            pred_col = _tpch_pick_pred_col(tables, idx + vi)
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_line_query(tables, conds, vec, pred_col, idx + vi)
            idx += 1

    # Bushy topologies
    bushy_topos = _tpch_bushy_topologies()
    for topo_label, shape, template, n_joins in bushy_topos:
        vecs = bench_vectors(n_joins)
        topo_tables = _tpch_tables_in(template)
        for vi, vec in enumerate(vecs[:5]):
            pred_col = _tpch_pick_pred_col(topo_tables, idx + vi)
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_bushy_query(template, vec, pred_col, idx + vi)
            idx += 1

    # Branch topologies
    branch_topos = _tpch_branch_topologies()
    for topo_label, shape, template, n_joins in branch_topos:
        vecs = bench_vectors(n_joins)
        topo_tables = _tpch_tables_in(template)
        for vi, vec in enumerate(vecs[:5]):
            pred_col = _tpch_pick_pred_col(topo_tables, idx + vi)
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_bushy_query(template, vec, pred_col, idx + vi)
            idx += 1

    # Aggregation variants. Each spec carries the topology that contains every
    # table its SELECT / GROUP BY columns reference, so the query binds. (All
    # topologies have >=2 joins so bench_vectors produces a valid join vector.)
    agg_specs = [
        {"select": "COUNT(*) AS cnt, SUM(l_extendedprice) AS rev", "group_by": "",
         "tables": ["customer", "orders", "lineitem"],
         "conds": ["c_custkey = o_custkey", "o_orderkey = l_orderkey"]},
        {"select": "o_orderpriority, COUNT(*) AS cnt", "group_by": "o_orderpriority",
         "tables": ["customer", "orders", "lineitem"],
         "conds": ["c_custkey = o_custkey", "o_orderkey = l_orderkey"]},
        {"select": "n_name, SUM(l_quantity) AS total_qty, AVG(l_extendedprice) AS avg_price",
         "group_by": "n_name",
         "tables": ["nation", "supplier", "lineitem"],
         "conds": ["n_nationkey = s_nationkey", "s_suppkey = l_suppkey"]},
        {"select": "s_nationkey, COUNT(*) AS cnt, MIN(ps_supplycost) AS min_cost",
         "group_by": "s_nationkey",
         "tables": ["nation", "supplier", "partsupp"],
         "conds": ["n_nationkey = s_nationkey", "s_suppkey = ps_suppkey"]},
        {"select": "r_name, COUNT(*) AS cnt, MAX(c_acctbal) AS max_bal", "group_by": "r_name",
         "tables": ["region", "nation", "customer"],
         "conds": ["r_regionkey = n_regionkey", "n_nationkey = c_nationkey"]},
        {"select": "c_mktsegment, SUM(o_totalprice) AS total_val", "group_by": "c_mktsegment",
         "tables": ["customer", "orders", "lineitem"],
         "conds": ["c_custkey = o_custkey", "o_orderkey = l_orderkey"]},
        {"select": "p_size, COUNT(*) AS cnt, AVG(l_discount) AS avg_disc", "group_by": "p_size",
         "tables": ["part", "lineitem", "orders"],
         "conds": ["p_partkey = l_partkey", "l_orderkey = o_orderkey"]},
        {"select": "n_regionkey, SUM(s_acctbal) AS tot_bal, COUNT(*) AS n_supp",
         "group_by": "n_regionkey",
         "tables": ["region", "nation", "supplier"],
         "conds": ["r_regionkey = n_regionkey", "n_nationkey = s_nationkey"]},
    ]
    for ai, agg in enumerate(agg_specs):
        tables, conds = agg["tables"], agg["conds"]
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        vec = vecs[(ai + 2) % len(vecs)]
        pred_col = _tpch_pick_pred_col(tables, idx + ai)
        label = f"th_agg{ai}"
        queries[label] = _build_line_query(tables, conds, vec, pred_col, idx + ai, agg=agg)
        idx += 1

    return queries


# ============================================================================
# TPC-DS SCHEMA
# ============================================================================
TPCDS_PRED_COLS = [
    "c_customer_sk", "c_birth_year", "ca_address_sk",
    "cd_demo_sk", "cd_purchase_estimate", "hd_demo_sk",
    "i_item_sk", "i_current_price", "i_wholesale_cost",
    "s_store_sk", "s_number_employees",
    "ss_item_sk", "ss_quantity", "ss_sales_price", "ss_net_profit",
    "ws_item_sk", "ws_quantity", "ws_sales_price",
    "cs_item_sk", "cs_quantity", "cs_sales_price",
    "d_date_sk", "d_year", "d_month_seq",
    "p_promo_sk", "ib_income_band_sk",
]


def _tpcds_line_topologies():
    topos = []
    topos.append(("ds_line3a",
                  ["store_sales", "customer", "customer_address"],
                  ["ss_customer_sk = c_customer_sk", "c_current_addr_sk = ca_address_sk"]))
    topos.append(("ds_line3b",
                  ["web_sales", "customer", "customer_demographics"],
                  ["ws_bill_customer_sk = c_customer_sk", "c_current_cdemo_sk = cd_demo_sk"]))
    topos.append(("ds_line3c",
                  ["store_sales", "item", "date_dim"],
                  ["ss_item_sk = i_item_sk", "ss_sold_date_sk = d_date_sk"]))
    topos.append(("ds_line4a",
                  ["store_sales", "customer", "customer_address", "customer_demographics"],
                  ["ss_customer_sk = c_customer_sk", "c_current_addr_sk = ca_address_sk",
                   "c_current_cdemo_sk = cd_demo_sk"]))
    topos.append(("ds_line4b",
                  ["web_sales", "customer", "customer_address", "household_demographics"],
                  ["ws_bill_customer_sk = c_customer_sk", "c_current_addr_sk = ca_address_sk",
                   "c_current_hdemo_sk = hd_demo_sk"]))
    topos.append(("ds_line5a",
                  ["store_sales", "item", "store", "customer", "customer_address"],
                  ["ss_item_sk = i_item_sk", "ss_store_sk = s_store_sk",
                   "ss_customer_sk = c_customer_sk", "c_current_addr_sk = ca_address_sk"]))
    topos.append(("ds_line5b",
                  ["web_sales", "item", "customer", "customer_demographics", "household_demographics"],
                  ["ws_item_sk = i_item_sk", "ws_bill_customer_sk = c_customer_sk",
                   "c_current_cdemo_sk = cd_demo_sk", "c_current_hdemo_sk = hd_demo_sk"]))
    topos.append(("ds_line6",
                  ["store_sales", "customer", "customer_address", "customer_demographics",
                   "household_demographics", "income_band"],
                  ["ss_customer_sk = c_customer_sk", "c_current_addr_sk = ca_address_sk",
                   "c_current_cdemo_sk = cd_demo_sk", "c_current_hdemo_sk = hd_demo_sk",
                   "hd_income_band_sk = ib_income_band_sk"]))
    topos.append(("ds_line7",
                  ["store_sales", "item", "store", "customer", "customer_address",
                   "customer_demographics", "household_demographics"],
                  ["ss_item_sk = i_item_sk", "ss_store_sk = s_store_sk",
                   "ss_customer_sk = c_customer_sk", "c_current_addr_sk = ca_address_sk",
                   "c_current_cdemo_sk = cd_demo_sk", "c_current_hdemo_sk = hd_demo_sk"]))
    topos.append(("ds_line8",
                  ["store_sales", "item", "store", "promotion", "customer", "customer_address",
                   "customer_demographics", "household_demographics"],
                  ["ss_item_sk = i_item_sk", "ss_store_sk = s_store_sk",
                   "ss_promo_sk = p_promo_sk", "ss_customer_sk = c_customer_sk",
                   "c_current_addr_sk = ca_address_sk", "c_current_cdemo_sk = cd_demo_sk",
                   "c_current_hdemo_sk = hd_demo_sk"]))
    return topos


def _tpcds_bushy_templates():
    topos = []
    topos.append(("ds_bushy4a", 3,
                  "(( store_sales {0} item ON ss_item_sk = i_item_sk) "
                  "{1} ( customer {2} customer_address ON c_current_addr_sk = ca_address_sk) "
                  "ON ss_customer_sk = c_customer_sk)"))
    topos.append(("ds_bushy4b", 3,
                  "(( web_sales {0} customer ON ws_bill_customer_sk = c_customer_sk) "
                  "{1} ( item {2} date_dim ON 1=1) "
                  "ON ws_item_sk = i_item_sk)"))
    topos.append(("ds_bushy5a", 4,
                  "((( store_sales {0} item ON ss_item_sk = i_item_sk) "
                  "{1} store ON ss_store_sk = s_store_sk) "
                  "{2} ( customer {3} customer_address ON c_current_addr_sk = ca_address_sk) "
                  "ON ss_customer_sk = c_customer_sk)"))
    topos.append(("ds_bushy6", 5,
                  "((( store_sales {0} item ON ss_item_sk = i_item_sk) "
                  "{1} ( customer {2} customer_address ON c_current_addr_sk = ca_address_sk) "
                  "ON ss_customer_sk = c_customer_sk) "
                  "{3} ( customer_demographics {4} household_demographics "
                  "ON 1=1) ON c_current_cdemo_sk = cd_demo_sk)"))
    topos.append(("ds_bushy4c", 3,
                  "(( store_sales {0} web_sales ON ss_customer_sk = ws_bill_customer_sk) "
                  "{1} ( customer {2} item ON 1=1) "
                  "ON ss_customer_sk = c_customer_sk)"))
    return topos


def gen_tpcds_queries():
    """Generate ~100 diverse TPC-DS queries."""
    queries = {}
    idx = 0

    # Line topologies
    line_topos = _tpcds_line_topologies()
    for topo_label, tables, conds in line_topos:
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[:5]):
            pred_col = TPCDS_PRED_COLS[(idx + vi) % len(TPCDS_PRED_COLS)]
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_line_query(tables, conds, vec, pred_col, idx + vi)
            idx += 1

    # Right-deep versions
    for topo_label, tables, conds in line_topos[:7]:
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[4:7]):
            pred_col = TPCDS_PRED_COLS[(idx + vi) % len(TPCDS_PRED_COLS)]
            label = f"{topo_label}_rd_v{vi}"
            queries[label] = _build_right_deep_query(tables, conds, vec, pred_col, idx + vi)
            idx += 1

    # Bushy topologies
    bushy_topos = _tpcds_bushy_templates()
    for topo_label, n_joins, template in bushy_topos:
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[:5]):
            pred_col = TPCDS_PRED_COLS[(idx + vi) % len(TPCDS_PRED_COLS)]
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_bushy_query(template, vec, pred_col, idx + vi)
            idx += 1

    # Aggregation variants
    agg_specs = [
        {"select": "ca_state, COUNT(*) AS cnt, SUM(ss_net_profit) AS profit",
         "group_by": "ca_state"},
        {"select": "i_category, AVG(ss_sales_price) AS avg_price",
         "group_by": "i_category"},
        {"select": "d_year, COUNT(*) AS cnt, SUM(ws_sales_price) AS tot",
         "group_by": "d_year"},
        {"select": "s_state, MIN(ss_sales_price) AS lo, MAX(ss_sales_price) AS hi",
         "group_by": "s_state"},
        {"select": "COUNT(*) AS cnt, SUM(cs_quantity) AS total_qty", "group_by": ""},
        {"select": "cd_gender, COUNT(*) AS cnt, AVG(ss_quantity) AS avg_qty",
         "group_by": "cd_gender"},
        {"select": "ca_zip, SUM(ss_sales_price) AS revenue", "group_by": "ca_zip"},
        {"select": "i_brand, COUNT(*) AS cnt, SUM(ws_quantity) AS tot_qty",
         "group_by": "i_brand"},
    ]
    agg_topos = [
        (["store_sales", "customer", "customer_address"],
         ["ss_customer_sk = c_customer_sk", "c_current_addr_sk = ca_address_sk"]),
        (["store_sales", "item", "store"],
         ["ss_item_sk = i_item_sk", "ss_store_sk = s_store_sk"]),
        (["web_sales", "customer", "date_dim"],
         ["ws_bill_customer_sk = c_customer_sk", "ws_sold_date_sk = d_date_sk"]),
        (["store_sales", "item", "store", "customer"],
         ["ss_item_sk = i_item_sk", "ss_store_sk = s_store_sk", "ss_customer_sk = c_customer_sk"]),
        (["catalog_sales", "item", "customer"],
         ["cs_item_sk = i_item_sk", "cs_bill_customer_sk = c_customer_sk"]),
        (["store_sales", "customer", "customer_demographics"],
         ["ss_customer_sk = c_customer_sk", "c_current_cdemo_sk = cd_demo_sk"]),
        (["store_sales", "customer", "customer_address"],
         ["ss_customer_sk = c_customer_sk", "c_current_addr_sk = ca_address_sk"]),
        (["web_sales", "item", "customer"],
         ["ws_item_sk = i_item_sk", "ws_bill_customer_sk = c_customer_sk"]),
    ]
    for ai, agg in enumerate(agg_specs):
        tables, conds = agg_topos[ai]
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        vec = vecs[(ai + 2) % len(vecs)]
        pred_col = TPCDS_PRED_COLS[(idx + ai) % len(TPCDS_PRED_COLS)]
        label = f"ds_agg{ai}"
        queries[label] = _build_line_query(tables, conds, vec, pred_col, idx + ai, agg=agg)
        idx += 1

    return queries


# ============================================================================
# JOB (IMDb) SCHEMA
# ============================================================================
JOB_PRED_COLS = [
    "t.id", "t.production_year", "t.kind_id",
    "ci.person_id", "ci.movie_id", "ci.role_id",
    "mc.movie_id", "mc.company_id",
    "mi.movie_id", "mi.info_type_id",
    "mk.movie_id", "mk.keyword_id",
    "n.id", "cn.id", "k.id",
    "an.person_id", "cc.movie_id",
]

# Pre-defined join paths through the IMDb schema
JOB_PATHS = [
    # 3-table paths
    (["title t", "cast_info ci", "name n"],
     ["t.id = ci.movie_id", "ci.person_id = n.id"]),
    (["title t", "movie_companies mc", "company_name cn"],
     ["t.id = mc.movie_id", "mc.company_id = cn.id"]),
    (["title t", "movie_keyword mk", "keyword k"],
     ["t.id = mk.movie_id", "mk.keyword_id = k.id"]),
    (["title t", "movie_info mi", "info_type it"],
     ["t.id = mi.movie_id", "mi.info_type_id = it.id"]),
    (["title t", "complete_cast cc", "comp_cast_type cct1"],
     ["t.id = cc.movie_id", "cc.subject_id = cct1.id"]),
    (["title t", "movie_link ml", "link_type lt"],
     ["t.id = ml.movie_id", "ml.link_type_id = lt.id"]),
    (["cast_info ci", "name n", "aka_name an"],
     ["ci.person_id = n.id", "n.id = an.person_id"]),

    # 4-table paths
    (["title t", "cast_info ci", "name n", "aka_name an"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = an.person_id"]),
    (["title t", "cast_info ci", "name n", "person_info pi"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = pi.person_id"]),
    (["title t", "cast_info ci", "role_type rt", "char_name chn"],
     ["t.id = ci.movie_id", "ci.role_id = rt.id", "ci.person_role_id = chn.id"]),
    (["title t", "movie_companies mc", "company_name cn", "company_type ct"],
     ["t.id = mc.movie_id", "mc.company_id = cn.id", "mc.company_type_id = ct.id"]),
    (["title t", "movie_info mi", "info_type it", "movie_info_idx mii"],
     ["t.id = mi.movie_id", "mi.info_type_id = it.id", "t.id = mii.movie_id"]),

    # 5-table paths
    (["title t", "cast_info ci", "name n", "aka_name an", "person_info pi"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = an.person_id",
      "n.id = pi.person_id"]),
    (["title t", "cast_info ci", "name n", "movie_companies mc", "company_name cn"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "t.id = mc.movie_id",
      "mc.company_id = cn.id"]),
    (["title t", "movie_keyword mk", "keyword k", "movie_info mi", "info_type it"],
     ["t.id = mk.movie_id", "mk.keyword_id = k.id", "t.id = mi.movie_id",
      "mi.info_type_id = it.id"]),
    (["title t", "cast_info ci", "role_type rt", "movie_keyword mk", "keyword k"],
     ["t.id = ci.movie_id", "ci.role_id = rt.id", "t.id = mk.movie_id",
      "mk.keyword_id = k.id"]),
    (["title t", "movie_companies mc", "company_name cn", "company_type ct", "movie_keyword mk"],
     ["t.id = mc.movie_id", "mc.company_id = cn.id", "mc.company_type_id = ct.id",
      "t.id = mk.movie_id"]),

    # 6-table paths
    (["title t", "cast_info ci", "name n", "aka_name an", "movie_companies mc", "company_name cn"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = an.person_id",
      "t.id = mc.movie_id", "mc.company_id = cn.id"]),
    (["title t", "cast_info ci", "name n", "role_type rt", "movie_keyword mk", "keyword k"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "ci.role_id = rt.id",
      "t.id = mk.movie_id", "mk.keyword_id = k.id"]),
    (["title t", "movie_info mi", "info_type it", "movie_keyword mk", "keyword k", "kind_type kt"],
     ["t.id = mi.movie_id", "mi.info_type_id = it.id", "t.id = mk.movie_id",
      "mk.keyword_id = k.id", "t.kind_id = kt.id"]),

    # 7-table paths
    (["title t", "cast_info ci", "name n", "aka_name an", "movie_companies mc",
      "company_name cn", "company_type ct"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = an.person_id",
      "t.id = mc.movie_id", "mc.company_id = cn.id", "mc.company_type_id = ct.id"]),
    (["title t", "cast_info ci", "name n", "role_type rt", "movie_info mi",
      "info_type it", "movie_keyword mk"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "ci.role_id = rt.id",
      "t.id = mi.movie_id", "mi.info_type_id = it.id", "t.id = mk.movie_id"]),

    # 8-table paths
    (["title t", "cast_info ci", "name n", "aka_name an", "movie_companies mc",
      "company_name cn", "company_type ct", "movie_keyword mk"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = an.person_id",
      "t.id = mc.movie_id", "mc.company_id = cn.id", "mc.company_type_id = ct.id",
      "t.id = mk.movie_id"]),
    (["title t", "cast_info ci", "name n", "role_type rt", "char_name chn",
      "movie_info mi", "info_type it", "kind_type kt"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "ci.role_id = rt.id",
      "ci.person_role_id = chn.id", "t.id = mi.movie_id", "mi.info_type_id = it.id",
      "t.kind_id = kt.id"]),

    # 9-table paths
    (["title t", "cast_info ci", "name n", "aka_name an", "person_info pi",
      "movie_companies mc", "company_name cn", "company_type ct", "movie_keyword mk"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = an.person_id",
      "n.id = pi.person_id", "t.id = mc.movie_id", "mc.company_id = cn.id",
      "mc.company_type_id = ct.id", "t.id = mk.movie_id"]),

    # 10-table paths
    (["title t", "cast_info ci", "name n", "aka_name an", "person_info pi",
      "movie_companies mc", "company_name cn", "company_type ct",
      "movie_keyword mk", "keyword k"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = an.person_id",
      "n.id = pi.person_id", "t.id = mc.movie_id", "mc.company_id = cn.id",
      "mc.company_type_id = ct.id", "t.id = mk.movie_id", "mk.keyword_id = k.id"]),

    # 11-table paths
    (["title t", "cast_info ci", "name n", "aka_name an", "person_info pi",
      "movie_companies mc", "company_name cn", "company_type ct",
      "movie_keyword mk", "keyword k", "movie_info mi"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = an.person_id",
      "n.id = pi.person_id", "t.id = mc.movie_id", "mc.company_id = cn.id",
      "mc.company_type_id = ct.id", "t.id = mk.movie_id", "mk.keyword_id = k.id",
      "t.id = mi.movie_id"]),

    # 12-table paths
    (["title t", "cast_info ci", "name n", "aka_name an", "person_info pi",
      "movie_companies mc", "company_name cn", "company_type ct",
      "movie_keyword mk", "keyword k", "movie_info mi", "info_type it"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = an.person_id",
      "n.id = pi.person_id", "t.id = mc.movie_id", "mc.company_id = cn.id",
      "mc.company_type_id = ct.id", "t.id = mk.movie_id", "mk.keyword_id = k.id",
      "t.id = mi.movie_id", "mi.info_type_id = it.id"]),

    # 13-table paths
    (["title t", "cast_info ci", "name n", "aka_name an", "person_info pi",
      "movie_companies mc", "company_name cn", "company_type ct",
      "movie_keyword mk", "keyword k", "movie_info mi", "info_type it",
      "kind_type kt"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = an.person_id",
      "n.id = pi.person_id", "t.id = mc.movie_id", "mc.company_id = cn.id",
      "mc.company_type_id = ct.id", "t.id = mk.movie_id", "mk.keyword_id = k.id",
      "t.id = mi.movie_id", "mi.info_type_id = it.id", "t.kind_id = kt.id"]),

    # 14-table paths
    (["title t", "cast_info ci", "name n", "aka_name an", "person_info pi",
      "movie_companies mc", "company_name cn", "company_type ct",
      "movie_keyword mk", "keyword k", "movie_info mi", "info_type it",
      "kind_type kt", "role_type rt"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = an.person_id",
      "n.id = pi.person_id", "t.id = mc.movie_id", "mc.company_id = cn.id",
      "mc.company_type_id = ct.id", "t.id = mk.movie_id", "mk.keyword_id = k.id",
      "t.id = mi.movie_id", "mi.info_type_id = it.id", "t.kind_id = kt.id",
      "ci.role_id = rt.id"]),

    # 15-table paths
    (["title t", "cast_info ci", "name n", "aka_name an", "person_info pi",
      "movie_companies mc", "company_name cn", "company_type ct",
      "movie_keyword mk", "keyword k", "movie_info mi", "info_type it",
      "kind_type kt", "role_type rt", "char_name chn"],
     ["t.id = ci.movie_id", "ci.person_id = n.id", "n.id = an.person_id",
      "n.id = pi.person_id", "t.id = mc.movie_id", "mc.company_id = cn.id",
      "mc.company_type_id = ct.id", "t.id = mk.movie_id", "mk.keyword_id = k.id",
      "t.id = mi.movie_id", "mi.info_type_id = it.id", "t.kind_id = kt.id",
      "ci.role_id = rt.id", "ci.person_role_id = chn.id"]),
]

# Bushy templates for JOB
JOB_BUSHY_TEMPLATES = [
    ("jb_bushy4a", 3,
     "(( title t {0} cast_info ci ON t.id = ci.movie_id) "
     "{1} ( movie_companies mc {2} company_name cn ON mc.company_id = cn.id) "
     "ON t.id = mc.movie_id)"),
    ("jb_bushy4b", 3,
     "(( title t {0} movie_keyword mk ON t.id = mk.movie_id) "
     "{1} ( cast_info ci {2} name n ON ci.person_id = n.id) "
     "ON t.id = ci.movie_id)"),
    ("jb_bushy5a", 4,
     "((( title t {0} cast_info ci ON t.id = ci.movie_id) "
     "{1} name n ON ci.person_id = n.id) "
     "{2} ( movie_keyword mk {3} keyword k ON mk.keyword_id = k.id) "
     "ON t.id = mk.movie_id)"),
    ("jb_bushy5b", 4,
     "(( title t {0} movie_info mi ON t.id = mi.movie_id) "
     "{1} (( movie_companies mc {2} company_name cn ON mc.company_id = cn.id) "
     "{3} company_type ct ON mc.company_type_id = ct.id) "
     "ON t.id = mc.movie_id)"),
    ("jb_bushy6a", 5,
     "((( title t {0} cast_info ci ON t.id = ci.movie_id) "
     "{1} name n ON ci.person_id = n.id) "
     "{2} (( movie_companies mc {3} company_name cn ON mc.company_id = cn.id) "
     "{4} company_type ct ON mc.company_type_id = ct.id) "
     "ON t.id = mc.movie_id)"),
    ("jb_bushy6b", 5,
     "((( title t {0} movie_keyword mk ON t.id = mk.movie_id) "
     "{1} keyword k ON mk.keyword_id = k.id) "
     "{2} (( movie_info mi {3} info_type it ON mi.info_type_id = it.id) "
     "{4} kind_type kt ON t.kind_id = kt.id) "
     "ON t.id = mi.movie_id)"),
    ("jb_bushy7", 6,
     "(((( title t {0} cast_info ci ON t.id = ci.movie_id) "
     "{1} name n ON ci.person_id = n.id) "
     "{2} role_type rt ON ci.role_id = rt.id) "
     "{3} (( movie_companies mc {4} company_name cn ON mc.company_id = cn.id) "
     "{5} company_type ct ON mc.company_type_id = ct.id) "
     "ON t.id = mc.movie_id)"),
]


def gen_job_queries():
    """Generate ~100 diverse JOB queries."""
    queries = {}
    idx = 0

    # Line (left-deep) topologies
    for path_tables, path_conds in JOB_PATHS:
        n_joins = len(path_conds)
        vecs = bench_vectors(n_joins)
        n_vecs = 5 if n_joins <= 4 else 3 if n_joins <= 7 else 2 if n_joins <= 10 else 1
        for vi, vec in enumerate(vecs[:n_vecs]):
            pred_col = JOB_PRED_COLS[(idx + vi) % len(JOB_PRED_COLS)]
            n_tables = len(path_tables)
            label = f"jb_line{n_tables}_{idx:03d}_v{vi}"
            queries[label] = _build_line_query(
                path_tables, path_conds, vec, pred_col, idx + vi, select_cols="*")
            idx += 1

    # Right-deep versions for shorter paths
    for path_tables, path_conds in JOB_PATHS[:15]:
        n_joins = len(path_conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[5:8]):
            pred_col = JOB_PRED_COLS[(idx + vi) % len(JOB_PRED_COLS)]
            n_tables = len(path_tables)
            label = f"jb_rd{n_tables}_{idx:03d}_v{vi}"
            queries[label] = _build_right_deep_query(
                path_tables, path_conds, vec, pred_col, idx + vi, select_cols="*")
            idx += 1

    # Bushy topologies
    for topo_label, n_joins, template in JOB_BUSHY_TEMPLATES:
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[:4]):
            pred_col = JOB_PRED_COLS[(idx + vi) % len(JOB_PRED_COLS)]
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_bushy_query(template, vec, pred_col, idx + vi)
            idx += 1

    # Aggregation variants
    agg_specs = [
        {"select": "t.production_year, COUNT(*) AS cnt",
         "group_by": "t.production_year"},
        {"select": "COUNT(*) AS total_rows, MIN(t.production_year) AS min_year, MAX(t.production_year) AS max_year",
         "group_by": ""},
        {"select": "ci.role_id, COUNT(*) AS cnt, AVG(t.production_year) AS avg_year",
         "group_by": "ci.role_id"},
        {"select": "cn.country_code, COUNT(*) AS cnt",
         "group_by": "cn.country_code"},
    ]
    agg_paths = JOB_PATHS[0:4]
    for ai, agg in enumerate(agg_specs):
        path_tables, path_conds = agg_paths[ai]
        n_joins = len(path_conds)
        vecs = bench_vectors(n_joins)
        vec = vecs[(ai + 3) % len(vecs)]
        pred_col = random.choice(JOB_PRED_COLS)
        label = f"jb_agg{ai}"
        queries[label] = _build_line_query(path_tables, path_conds, vec, pred_col, idx,
                                           agg=agg)
        idx += 1

    return queries


# ============================================================================
# Bench output helpers
# ============================================================================
def write_bench_queries(queries, outdir, prefix):
    """Write all bench queries as individual .sql files (wipes old ones first)."""
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.endswith(".sql"):
            os.remove(os.path.join(outdir, f))
    for label, sql in sorted(queries.items()):
        fname = f"{prefix}_{label}.sql"
        with open(os.path.join(outdir, fname), "w") as f:
            f.write(sql + "\n")
    return len(queries)


def verify_bench_queries(queries, name):
    """Print statistics about generated bench queries."""
    total = len(queries)
    left_cnt = sum(1 for q in queries.values() if "LEFT OUTER JOIN" in q)
    right_cnt = sum(1 for q in queries.values() if "RIGHT OUTER JOIN" in q)
    full_cnt = sum(1 for q in queries.values() if "FULL OUTER JOIN" in q)
    inner_cnt = sum(1 for q in queries.values() if "INNER JOIN" in q)
    outer_per_q = []
    for q in queries.values():
        cnt = len(re.findall(r"(LEFT|RIGHT|FULL) OUTER JOIN", q))
        outer_per_q.append(cnt)
    min_outer = min(outer_per_q) if outer_per_q else 0
    banned = ["ROW_NUMBER", "RANK", "DENSE_RANK", "NTILE",
              "ARRAY_AGG", "STRING_AGG", "LIST(", "FIRST(", "LAST(",
              "ANY_VALUE", "INITCAP"]
    violations = []
    for label, q in queries.items():
        for b in banned:
            if b in q.upper():
                violations.append((label, b))
    print(f"\n{'='*60}")
    print(f"  {name}: {total} queries")
    print(f"  Queries with LEFT:  {left_cnt}  RIGHT: {right_cnt}  FULL: {full_cnt}  INNER: {inner_cnt}")
    print(f"  Min outer joins per query: {min_outer}")
    print(f"  Banned function violations: {len(violations)}")
    if violations:
        for l, b in violations[:5]:
            print(f"    {l}: contains {b}")
    print(f"{'='*60}")


# --- bench top-level generators -----------------------------------------------
def gen_bench_tpch():
    q = gen_tpch_queries()
    n = write_bench_queries(q, TPCH_DIR, "oy_th")
    verify_bench_queries(q, "TPC-H")
    print(f"  tpch/: {n} files written")

def gen_bench_tpcds():
    q = gen_tpcds_queries()
    n = write_bench_queries(q, TPCDS_DIR, "oy_ds")
    verify_bench_queries(q, "TPC-DS")
    print(f"  tpcds/: {n} files written")

def gen_bench_job():
    q = gen_job_queries()
    n = write_bench_queries(q, JOB_DIR, "oy_jb")
    verify_bench_queries(q, "JOB")
    print(f"  job/: {n} files written")


# --- validate: EXPLAIN each query against its DB, remove broken ones ---------
def validate_dir(db_path: str, query_dir: str, label: str):
    """EXPLAIN each query in query_dir against db_path; delete broken pairs."""
    import subprocess
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    duckdb_bin = os.path.join(repo_root, "build", "release", "duckdb")
    if not os.path.isfile(db_path):
        print(f"  [{label}] SKIP — db not found: {db_path}")
        return
    if not os.path.isfile(duckdb_bin):
        print(f"  [{label}] SKIP — duckdb binary not found: {duckdb_bin}")
        return
    files = sorted(f for f in os.listdir(query_dir) if f.endswith(".sql") and not f.endswith("_off.sql"))
    removed = 0
    for fname in files:
        fpath = os.path.join(query_dir, fname)
        with open(fpath) as fh:
            sql = fh.read()
        lines = [l for l in sql.splitlines() if not l.strip().upper().startswith("SET ")]
        explain_sql = "EXPLAIN " + "\n".join(lines)
        try:
            r = subprocess.run([duckdb_bin, db_path], input=explain_sql, capture_output=True,
                               text=True, timeout=10)
            if r.returncode != 0 or any(kw in (r.stderr + r.stdout).lower()
                                        for kw in ("error", "binder", "catalog")):
                off = fpath.replace(".sql", "_off.sql")
                os.remove(fpath)
                if os.path.isfile(off):
                    os.remove(off)
                removed += 1
        except (subprocess.TimeoutExpired, OSError):
            pass
    remaining = len(files) - removed
    print(f"  [{label}] validated: {remaining} ok, {removed} removed")

def gen_validate():
    """Validate all query families against their databases."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    validate_dir(os.path.join(repo_root, "graph_db"),
                 os.path.join(BASE, "graph"), "graph")
    validate_dir(os.path.join(repo_root, "tpch_db"),
                 os.path.join(BASE, "tpch"), "tpch")
    validate_dir(os.path.join(repo_root, "tpcds_db"),
                 os.path.join(BASE, "tpcds"), "tpcds")
    validate_dir(os.path.join(repo_root, "job_db"),
                 os.path.join(BASE, "job"), "job")


# --- dispatch ----------------------------------------------------------------
TARGETS = {
    "graph":    [gen_graph_pred],
    "pred":     [gen_graph_pred],
    "tpch":     [gen_bench_tpch],
    "tpcds":    [gen_bench_tpcds],
    "job":      [gen_bench_job],
    "bench":    [gen_bench_tpch, gen_bench_tpcds, gen_bench_job],
    "validate": [gen_validate],
    "all":      [gen_graph_pred, gen_bench_tpch, gen_bench_tpcds,
                 gen_bench_job],
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
