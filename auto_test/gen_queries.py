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


def _graph_variants(prefixes, selectivities):
    return {
        f"graph/{prefix}_{selectivity}.sql"
        for prefix in prefixes
        for selectivity in selectivities
    }


# Empirical corpus pruning from the SF100/bitcoin run started 2026-07-20
# 00:45:09. Only queries present in that partial report are classified here.
# A query is considered too fast only when both unprofiled T1 variants are
# below 0.5 seconds; this deliberately retains rdeep_N4_mixB_s01, whose
# DuckDB/OuterYan T1 values were 45.673/0.426 seconds.
FAST_CORPUS_EXCLUSIONS = (
    _graph_variants(
        ("bushyBal_N4_mixA", "bushyBal_N4_mixB", "line_N4_mixA"),
        ("s01",),
    )
    | _graph_variants(
        ("line_N3_mixB", "rdeep_N3_mixC"),
        ("s01", "s05", "s10", "s20", "s33", "s50"),
    )
)

TIMEOUT_CORPUS_EXCLUSIONS = (
    _graph_variants(
        ("bushyBal_N4_mixA", "bushyBal_N4_mixB", "line_N4_mixA", "rdeep_N4_mixB"),
        ("s50", "s67", "s80", "s95"),
    )
    | _graph_variants(
        ("bushyBal_N6_mixA", "bushy_N6_mixB"),
        ("s01", "s05", "s10", "s20", "s33", "s50", "s67", "s80", "s95"),
    )
    | _graph_variants(
        ("bushy_N5_mixA", "bushy_N5_mixC"),
        ("s05", "s10", "s20", "s33", "s50", "s67", "s80", "s95"),
    )
    | {"tpch/oy_th_real_order_full.sql"}
)

EXCLUDED_CORPUS_QUERIES = FAST_CORPUS_EXCLUSIONS | TIMEOUT_CORPUS_EXCLUSIONS


def is_excluded_query(outdir, filename):
    relative_path = os.path.relpath(os.path.join(outdir, filename), BASE)
    return relative_path.replace(os.sep, "/") in EXCLUDED_CORPUS_QUERIES

# ----------------------------------------------------------------------------
# Shape-mix policy — applies to EVERY corpus (graph, tpch, tpcds, job).
# BUSHY is the dominant shape: that is where OuterYan's join reordering +
# semi-join reduction produce performance gains. A few LEFT-deep (line/star)
# and RIGHT-deep variants are kept so the corpus still covers the whole
# join-tree-shape space. Right-deep is emitted ONLY for chain topologies (see
# _is_chain) — star/clique right-deep yields correlated-join (LATERAL) errors.
# Tune the mix here in one place.
# ----------------------------------------------------------------------------
SHAPE_LINE_VECS = 1     # left-deep (and star) variants per topology
SHAPE_RD_VECS = 2       # right-deep variants per chain topology
SHAPE_BUSHY_VECS = 6    # bushy/branch variants per template (dominant shape)


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
    filename = f"{label}.sql"
    if is_excluded_query(outdir, filename):
        return False
    with open(os.path.join(outdir, filename), "w") as f:
        f.write(sql + "\n")
    return True


def emit(outdir, queries):
    """Write all pairs into outdir (creating it); does NOT wipe pre-existing files."""
    os.makedirs(outdir, exist_ok=True)
    emitted = 0
    for label, sql in queries.items():
        emitted += int(write_pair(outdir, label, sql))
    return emitted


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
    """Bushy-dominant base join expressions (no SELECT/WHERE), all referencing R1
    (predicates filter R1.src). Per the shape-mix policy: mostly bushy, with a
    few left-deep (line) and right-deep bases for tree-shape coverage. All use
    mixed join types (no all-same-direction). Graph relations all expose
    src/dst, so every tree shape binds."""
    return {
        # --- BUSHY (dominant) ---
        "bushyBal_N4_mixB":  jn(jn(lf(1), lf(2), "FULL", 1, 2),
                                jn(lf(3), lf(4), "RIGHT", 3, 4), "LEFT", 2, 3)["sql"],
        "bushyBal_N4_mixA":  jn(jn(lf(1), lf(2), "LEFT", 1, 2),
                                jn(lf(3), lf(4), "INNER", 3, 4), "RIGHT", 2, 3)["sql"],
        "bushy_N5_mixC":     jn(jn(lf(1), lf(2), "RIGHT", 1, 2),
                                jn(jn(lf(3), lf(4), "FULL", 3, 4), lf(5), "LEFT", 4, 5),
                                "INNER", 2, 3)["sql"],
        "bushy_N5_mixA":     jn(jn(jn(lf(1), lf(2), "LEFT", 1, 2), lf(3), "FULL", 2, 3),
                                jn(lf(4), lf(5), "RIGHT", 4, 5), "INNER", 3, 4)["sql"],
        "bushyBal_N6_mixA":  jn(jn(jn(lf(1), lf(2), "LEFT", 1, 2), lf(3), "INNER", 2, 3),
                                jn(jn(lf(4), lf(5), "RIGHT", 4, 5), lf(6), "FULL", 5, 6),
                                "LEFT", 3, 4)["sql"],
        "bushy_N6_mixB":     jn(jn(jn(lf(1), lf(2), "FULL", 1, 2), lf(3), "RIGHT", 2, 3),
                                jn(jn(lf(4), lf(5), "LEFT", 4, 5), lf(6), "INNER", 5, 6),
                                "FULL", 3, 4)["sql"],
        # --- LEFT-deep (several, for shape coverage) ---
        "line_N3_mixB":      jn(jn(lf(1), lf(2), "FULL", 1, 2), lf(3), "RIGHT", 2, 3)["sql"],
        "line_N4_mixA":      jn(jn(jn(lf(1), lf(2), "LEFT", 1, 2), lf(3), "INNER", 2, 3),
                                lf(4), "RIGHT", 3, 4)["sql"],
        # --- RIGHT-deep (several, for shape coverage) ---
        "rdeep_N3_mixC":     jn(lf(1), jn(lf(2), lf(3), "FULL", 2, 3), "RIGHT", 1, 2)["sql"],
        "rdeep_N4_mixB":     jn(lf(1), jn(lf(2), jn(lf(3), lf(4), "LEFT", 3, 4),
                                "INNER", 2, 3), "FULL", 1, 2)["sql"],
    }


def gen_graph_pred():
    wipe(PRED_DIR)
    n = 0
    for bname, expr in pred_bases().items():
        for pname, pred in GRAPH_PREDS.items():
            n += int(write_pair(PRED_DIR, f"{bname}_{pname}",
                                f"SELECT * FROM {expr} WHERE {pred};"))
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


# --- Aggregation: one aggregate per query, over COUNT/SUM/MIN/MAX (no AVG) ---
# OuterYan's aggregate handling supports a single aggregate function per query,
# and AVG is intentionally excluded. Each agg query is built from a "base"
# (a topology + an in-scope GROUP BY column + an in-scope numeric measure +
# an in-scope predicate column); the base is expanded into one query per
# aggregate function below.
AGG_FUNCS = [("cnt", "COUNT(*)"), ("total", "SUM({m})"),
             ("lo", "MIN({m})"), ("hi", "MAX({m})")]


def _expand_agg_bases(bases):
    """Expand each base into one single-aggregate spec per AGG_FUNCS entry."""
    specs = []
    for b in bases:
        for suf, tmpl in AGG_FUNCS:
            expr = tmpl.format(m=b["measure"])
            grp = b.get("group", "")
            sel = f"{grp}, {expr} AS {suf}_val" if grp else f"{expr} AS {suf}_val"
            specs.append({"select": sel, "group_by": grp,
                          "tables": b["tables"], "conds": b["conds"],
                          "pred_col": b["pred_col"]})
    return specs


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


# --- Generic schema-aware predicate selection (reused by TPC-DS and JOB) -----
# Same idea as the _tpch_* helpers above, parameterised by a {table: col-prefix}
# map so it works for any schema. A generated WHERE predicate only binds if its
# column belongs to a table actually present in the topology.
def _col_table_pm(col, prefix_map):
    """Table a column belongs to, by longest matching (underscore-anchored) prefix."""
    best = None
    for tbl, pre in prefix_map.items():
        if col.startswith(pre) and (best is None or len(pre) > len(prefix_map[best])):
            best = tbl
    return best


def _tables_in_text(text, all_tables):
    """Set of known tables named in a FROM fragment / bushy template."""
    low = text.lower()
    return {t for t in all_tables if re.search(r"\b" + re.escape(t) + r"\b", low)}


def _pick_pred_pm(tables, idx, pred_cols, prefix_map):
    """Pick a predicate column whose table is in `tables` (else fall back)."""
    tabs = set(tables)
    allowed = [c for c in pred_cols if _col_table_pm(c, prefix_map) in tabs]
    if not allowed:
        allowed = pred_cols
    return allowed[idx % len(allowed)]


def _is_chain(tables, conds, col_to_group):
    """True iff each cond[i] references exactly {tables[i], tables[i+1]} — a
    linear chain. Right-deep nesting (t0 J (t1 J (t2 J ...))) only binds for
    chains; on a star/clique topology a deep join condition references a table
    outside its parenthesised scope, which DuckDB rejects as a correlated /
    LATERAL join ("Non-inner join on correlated columns not supported")."""
    for i, cond in enumerate(conds):
        groups = set()
        for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", cond):
            g = col_to_group(tok)
            if g:
                groups.add(g)
        if groups != {tables[i], tables[i + 1]}:
            return False
    return True


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


def _tpch_realistic_queries():
    """Real-semantics TPC-H queries: actual tables, FK joins, meaningful
    projections/predicates — NOT shape probes. Flat (no subqueries/CTEs) and
    each has >= 3 outer joins. The only outer join in canonical TPC-H is Q13
    (customer LEFT JOIN orders); these extend that pattern with more
    outer-joined tables and add FULL/RIGHT variants for join-type coverage."""
    return {
        # Q13 spirit, flattened to one level + extended: customer activity,
        # keeping customers with no orders / orders with no lineitems.
        "real_custdist": (
            "SELECT c_custkey, c_name, count(l_orderkey) AS line_cnt\n"
            "FROM customer\n"
            "    LEFT OUTER JOIN orders   ON c_custkey = o_custkey\n"
            "    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey\n"
            "    LEFT OUTER JOIN nation   ON c_nationkey = n_nationkey\n"
            "WHERE c_acctbal > 0\n"
            "GROUP BY c_custkey, c_name;"),
        # Customer order/line detail with geography (4 LEFT outer joins).
        "real_cust_order_line": (
            "SELECT c_custkey, c_name, n_name, o_orderdate, l_quantity, l_extendedprice\n"
            "FROM customer\n"
            "    LEFT OUTER JOIN orders   ON c_custkey = o_custkey\n"
            "    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey\n"
            "    LEFT OUTER JOIN nation   ON c_nationkey = n_nationkey\n"
            "    LEFT OUTER JOIN region   ON n_regionkey = r_regionkey\n"
            "WHERE c_acctbal > 1000;"),
        # Supplier supply catalog with geography (4 LEFT outer joins).
        "real_supplier_catalog": (
            "SELECT s_name, n_name, r_name, p_name, ps_availqty\n"
            "FROM supplier\n"
            "    LEFT OUTER JOIN partsupp ON s_suppkey = ps_suppkey\n"
            "    LEFT OUTER JOIN part     ON ps_partkey = p_partkey\n"
            "    LEFT OUTER JOIN nation   ON s_nationkey = n_nationkey\n"
            "    LEFT OUTER JOIN region   ON n_regionkey = r_regionkey\n"
            "WHERE s_acctbal > 1000;"),
        # Region -> nation -> {customers, suppliers}: branch/Y, 3 outer joins.
        "real_region_branch": (
            "SELECT r_name, n_name, c_name, s_name\n"
            "FROM region\n"
            "    LEFT OUTER JOIN nation   ON r_regionkey = n_regionkey\n"
            "    LEFT OUTER JOIN customer ON n_nationkey = c_nationkey\n"
            "    LEFT OUTER JOIN supplier ON n_nationkey = s_nationkey\n"
            "WHERE r_regionkey < 4;"),
        # Order/line/part with a FULL outer join (3 outer joins, mixed types).
        "real_order_full": (
            "SELECT o_orderkey, o_orderstatus, l_linestatus, p_brand, ps_availqty\n"
            "FROM orders\n"
            "    FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey\n"
            "    LEFT OUTER JOIN part     ON l_partkey = p_partkey\n"
            "    LEFT OUTER JOIN partsupp ON l_partkey = ps_partkey AND l_suppkey = ps_suppkey\n"
            "WHERE o_totalprice > 50000;"),
        # Supplier supply with a RIGHT outer join anchor (3 outer joins).
        "real_supplier_right": (
            "SELECT n_name, s_name, ps_availqty, p_name\n"
            "FROM nation\n"
            "    RIGHT OUTER JOIN supplier ON n_nationkey = s_nationkey\n"
            "    LEFT OUTER JOIN partsupp  ON s_suppkey = ps_suppkey\n"
            "    LEFT OUTER JOIN part      ON ps_partkey = p_partkey\n"
            "WHERE s_acctbal > 500;"),
    }


def gen_tpch_queries():
    """Generate ~100 diverse TPC-H queries."""
    queries = {}
    idx = 0

    # Line topologies (left-deep) — a few for shape coverage
    line_topos = _tpch_line_topologies()
    for topo_label, tables, conds, shape in line_topos:
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[:SHAPE_LINE_VECS]):
            pred_col = _tpch_pick_pred_col(tables, idx + vi)
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_line_query(tables, conds, vec, pred_col, idx + vi)
            idx += 1

    # Right-deep versions (chain topologies only — see _is_chain)
    for topo_label, tables, conds, shape in line_topos[:6]:
        if not _is_chain(tables, conds, _tpch_col_table):
            continue
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[3:3 + SHAPE_RD_VECS]):
            pred_col = _tpch_pick_pred_col(tables, idx + vi)
            label = f"{topo_label}_rd_v{vi}"
            queries[label] = _build_right_deep_query(tables, conds, vec, pred_col, idx + vi)
            idx += 1

    # Star topologies (left-deep over a star graph) — a few for coverage
    star_topos = _tpch_star_topologies()
    for topo_label, tables, conds, shape in star_topos:
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[:SHAPE_LINE_VECS]):
            pred_col = _tpch_pick_pred_col(tables, idx + vi)
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_line_query(tables, conds, vec, pred_col, idx + vi)
            idx += 1

    # Bushy topologies (DOMINANT shape)
    bushy_topos = _tpch_bushy_topologies()
    for topo_label, shape, template, n_joins in bushy_topos:
        vecs = bench_vectors(n_joins)
        topo_tables = _tpch_tables_in(template)
        for vi, vec in enumerate(vecs[:SHAPE_BUSHY_VECS]):
            pred_col = _tpch_pick_pred_col(topo_tables, idx + vi)
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_bushy_query(template, vec, pred_col, idx + vi)
            idx += 1

    # Branch/Y topologies (bushy family — DOMINANT shape)
    branch_topos = _tpch_branch_topologies()
    for topo_label, shape, template, n_joins in branch_topos:
        vecs = bench_vectors(n_joins)
        topo_tables = _tpch_tables_in(template)
        for vi, vec in enumerate(vecs[:SHAPE_BUSHY_VECS]):
            pred_col = _tpch_pick_pred_col(topo_tables, idx + vi)
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_bushy_query(template, vec, pred_col, idx + vi)
            idx += 1

    # Aggregation variants. Each base carries a topology plus an in-scope GROUP
    # BY column, numeric measure, and predicate column, so the query binds. The
    # base is expanded into one query per aggregate (COUNT/SUM/MIN/MAX, no AVG).
    # (All topologies have >=2 joins so bench_vectors yields a valid vector.)
    agg_bases = [
        {"tables": ["customer", "orders", "lineitem"],
         "conds": ["c_custkey = o_custkey", "o_orderkey = l_orderkey"],
         "group": "o_orderpriority", "measure": "l_extendedprice", "pred_col": "o_orderkey"},
        {"tables": ["nation", "supplier", "partsupp"],
         "conds": ["n_nationkey = s_nationkey", "s_suppkey = ps_suppkey"],
         "group": "s_nationkey", "measure": "ps_supplycost", "pred_col": "ps_availqty"},
        {"tables": ["region", "nation", "customer"],
         "conds": ["r_regionkey = n_regionkey", "n_nationkey = c_nationkey"],
         "group": "r_name", "measure": "c_acctbal", "pred_col": "c_custkey"},
        {"tables": ["part", "lineitem", "orders"],
         "conds": ["p_partkey = l_partkey", "l_orderkey = o_orderkey"],
         "group": "p_size", "measure": "o_totalprice", "pred_col": "l_linenumber"},
    ]
    for ai, agg in enumerate(_expand_agg_bases(agg_bases)):
        tables, conds = agg["tables"], agg["conds"]
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        vec = vecs[ai % len(vecs)]
        label = f"th_agg{ai}"
        queries[label] = _build_line_query(tables, conds, vec, agg["pred_col"], idx + ai, agg=agg)
        idx += 1

    # Real-semantics queries (derived from the only outer-join TPC-H query, Q13)
    queries.update(_tpch_realistic_queries())
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

# {table: column-prefix} for the tables used by the TPC-DS topologies. Prefixes
# are underscore-anchored so e.g. ss_ (store_sales) / s_ (store), ca_/cd_/cs_/c_
# never collide.
TPCDS_TABLE_PREFIX = {
    "store_sales": "ss_", "web_sales": "ws_", "catalog_sales": "cs_",
    "customer": "c_", "customer_address": "ca_", "customer_demographics": "cd_",
    "household_demographics": "hd_", "item": "i_", "store": "s_",
    "date_dim": "d_", "promotion": "p_", "income_band": "ib_",
}
TPCDS_ALL_TABLES = list(TPCDS_TABLE_PREFIX)


def _tpcds_col_table(col):
    return _col_table_pm(col, TPCDS_TABLE_PREFIX)


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
    topos.append(("ds_bushy4d", 3,
                  "(( store_sales {0} item ON ss_item_sk = i_item_sk) "
                  "{1} ( customer {2} date_dim ON 1=1) "
                  "ON ss_customer_sk = c_customer_sk)"))
    topos.append(("ds_bushy4e", 3,
                  "(( web_sales {0} item ON ws_item_sk = i_item_sk) "
                  "{1} ( customer {2} customer_address ON c_current_addr_sk = ca_address_sk) "
                  "ON ws_bill_customer_sk = c_customer_sk)"))
    topos.append(("ds_bushy4f", 3,
                  "(( catalog_sales {0} item ON cs_item_sk = i_item_sk) "
                  "{1} ( customer {2} date_dim ON 1=1) "
                  "ON cs_bill_customer_sk = c_customer_sk)"))
    topos.append(("ds_bushy4g", 3,
                  "(( store_sales {0} store ON ss_store_sk = s_store_sk) "
                  "{1} ( customer {2} customer_demographics ON c_current_cdemo_sk = cd_demo_sk) "
                  "ON ss_customer_sk = c_customer_sk)"))
    topos.append(("ds_bushy5b", 4,
                  "((( store_sales {0} item ON ss_item_sk = i_item_sk) "
                  "{1} promotion ON ss_promo_sk = p_promo_sk) "
                  "{2} ( customer {3} customer_address ON c_current_addr_sk = ca_address_sk) "
                  "ON ss_customer_sk = c_customer_sk)"))
    return topos


def _tpcds_realistic_queries():
    """Real-semantics TPC-DS queries: actual fact/dimension tables, FK joins,
    meaningful projections/predicates. Flat (no subqueries/CTEs) — note the
    canonical outer-join queries Q51/Q97 FULL-OUTER-JOIN pre-aggregated channel
    subqueries; flattened here as fact-with-dimension reports that keep all
    fact rows. Each has >= 3 outer joins (mostly LEFT, with FULL/RIGHT for
    coverage)."""
    return {
        # Store-sales decorated with its dimensions, keeping every sale even
        # when a dimension key is missing (4 LEFT outer joins). Q5/Q40 spirit.
        "real_store_dims": (
            "SELECT ss_item_sk, ss_sales_price, i_brand, c_first_name, s_store_name\n"
            "FROM store_sales\n"
            "    LEFT OUTER JOIN item      ON ss_item_sk = i_item_sk\n"
            "    LEFT OUTER JOIN customer  ON ss_customer_sk = c_customer_sk\n"
            "    LEFT OUTER JOIN store     ON ss_store_sk = s_store_sk\n"
            "    LEFT OUTER JOIN promotion ON ss_promo_sk = p_promo_sk\n"
            "WHERE ss_quantity > 0;"),
        # Web sales with customer geography + date (3 LEFT outer joins).
        "real_web_geo": (
            "SELECT ws_item_sk, ws_sales_price, c_last_name, ca_state, d_year\n"
            "FROM web_sales\n"
            "    LEFT OUTER JOIN customer         ON ws_bill_customer_sk = c_customer_sk\n"
            "    LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk\n"
            "    LEFT OUTER JOIN date_dim         ON ws_sold_date_sk = d_date_sk\n"
            "WHERE ws_quantity > 0;"),
        # Catalog sales with customer demographics + item (3 LEFT outer joins).
        "real_catalog_demo": (
            "SELECT cs_item_sk, cs_sales_price, cd_gender, i_category\n"
            "FROM catalog_sales\n"
            "    LEFT OUTER JOIN customer               ON cs_bill_customer_sk = c_customer_sk\n"
            "    LEFT OUTER JOIN customer_demographics  ON c_current_cdemo_sk = cd_demo_sk\n"
            "    LEFT OUTER JOIN item                   ON cs_item_sk = i_item_sk\n"
            "WHERE cs_quantity > 0;"),
        # Cross-channel item presence (Q97 spirit): items and their store +
        # catalog sales, FULL outer join so items in only one channel survive.
        "real_channel_full": (
            "SELECT i_item_sk, i_brand, ss_sales_price, cs_sales_price, d_year\n"
            "FROM item\n"
            "    LEFT OUTER JOIN store_sales   ON i_item_sk = ss_item_sk\n"
            "    FULL OUTER JOIN catalog_sales ON i_item_sk = cs_item_sk\n"
            "    LEFT OUTER JOIN date_dim      ON ss_sold_date_sk = d_date_sk\n"
            "WHERE i_category IS NOT NULL;"),
        # Store sales joined through the customer-demographics dimensions
        # (4 LEFT outer joins).
        "real_store_demo": (
            "SELECT ss_item_sk, ss_net_profit, cd_gender, hd_demo_sk, ca_state\n"
            "FROM store_sales\n"
            "    LEFT OUTER JOIN customer               ON ss_customer_sk = c_customer_sk\n"
            "    LEFT OUTER JOIN customer_demographics  ON c_current_cdemo_sk = cd_demo_sk\n"
            "    LEFT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk\n"
            "    LEFT OUTER JOIN customer_address       ON c_current_addr_sk = ca_address_sk\n"
            "WHERE ss_net_profit > 0;"),
        # Items sold per category, keeping unsold/dimensionless sales
        # (single COUNT aggregate, no AVG; 3 outer joins).
        "real_store_agg": (
            "SELECT i_category, count(ss_item_sk) AS sold_cnt\n"
            "FROM store_sales\n"
            "    LEFT OUTER JOIN item     ON ss_item_sk = i_item_sk\n"
            "    LEFT OUTER JOIN store    ON ss_store_sk = s_store_sk\n"
            "    LEFT OUTER JOIN customer ON ss_customer_sk = c_customer_sk\n"
            "WHERE ss_quantity > 0\n"
            "GROUP BY i_category;"),
    }


def gen_tpcds_queries():
    """Generate ~100 diverse TPC-DS queries."""
    queries = {}
    idx = 0

    # Line topologies (left-deep) — a few for shape coverage
    line_topos = _tpcds_line_topologies()
    for topo_label, tables, conds in line_topos:
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[:SHAPE_LINE_VECS]):
            pred_col = _pick_pred_pm(tables, idx + vi, TPCDS_PRED_COLS, TPCDS_TABLE_PREFIX)
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_line_query(tables, conds, vec, pred_col, idx + vi)
            idx += 1

    # Right-deep versions (chain topologies only — star right-deep would emit a
    # correlated/LATERAL join that DuckDB rejects)
    for topo_label, tables, conds in line_topos[:7]:
        if not _is_chain(tables, conds, _tpcds_col_table):
            continue
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[4:4 + SHAPE_RD_VECS]):
            pred_col = _pick_pred_pm(tables, idx + vi, TPCDS_PRED_COLS, TPCDS_TABLE_PREFIX)
            label = f"{topo_label}_rd_v{vi}"
            queries[label] = _build_right_deep_query(tables, conds, vec, pred_col, idx + vi)
            idx += 1

    # Bushy topologies (DOMINANT shape)
    bushy_topos = _tpcds_bushy_templates()
    for topo_label, n_joins, template in bushy_topos:
        vecs = bench_vectors(n_joins)
        topo_tables = _tables_in_text(template, TPCDS_ALL_TABLES)
        for vi, vec in enumerate(vecs[:SHAPE_BUSHY_VECS]):
            pred_col = _pick_pred_pm(topo_tables, idx + vi, TPCDS_PRED_COLS, TPCDS_TABLE_PREFIX)
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_bushy_query(template, vec, pred_col, idx + vi)
            idx += 1

    # Aggregation variants — one aggregate per query (COUNT/SUM/MIN/MAX, no
    # AVG). Each base lists in-scope group/measure/predicate columns so the
    # query binds, then is expanded over the four aggregate functions.
    agg_bases = [
        {"tables": ["store_sales", "customer", "customer_address"],
         "conds": ["ss_customer_sk = c_customer_sk", "c_current_addr_sk = ca_address_sk"],
         "group": "ca_state", "measure": "ss_net_profit", "pred_col": "ss_quantity"},
        {"tables": ["store_sales", "item", "store"],
         "conds": ["ss_item_sk = i_item_sk", "ss_store_sk = s_store_sk"],
         "group": "i_category", "measure": "ss_sales_price", "pred_col": "ss_quantity"},
        {"tables": ["web_sales", "customer", "date_dim"],
         "conds": ["ws_bill_customer_sk = c_customer_sk", "ws_sold_date_sk = d_date_sk"],
         "group": "d_year", "measure": "ws_sales_price", "pred_col": "ws_quantity"},
        {"tables": ["catalog_sales", "item", "customer"],
         "conds": ["cs_item_sk = i_item_sk", "cs_bill_customer_sk = c_customer_sk"],
         "group": "i_brand", "measure": "cs_sales_price", "pred_col": "cs_quantity"},
    ]
    for ai, agg in enumerate(_expand_agg_bases(agg_bases)):
        tables, conds = agg["tables"], agg["conds"]
        n_joins = len(conds)
        vecs = bench_vectors(n_joins)
        vec = vecs[ai % len(vecs)]
        label = f"ds_agg{ai}"
        queries[label] = _build_line_query(tables, conds, vec, agg["pred_col"], idx + ai, agg=agg)
        idx += 1

    # Real-semantics queries (derived from the outer-join TPC-DS queries:
    # Q5/Q40/Q49/Q72/Q80/Q93 LEFT, Q51/Q97 FULL)
    queries.update(_tpcds_realistic_queries())
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

# JOB columns are alias-qualified (e.g. "ci.role_id"), so "in scope" means the
# alias is present in the topology. These helpers mirror _pick_pred_pm/_is_chain
# but key on the table ALIAS instead of a column prefix.
def _job_aliases_in(text):
    """Aliases referenced as `alias.` in a JOB join template / FROM fragment."""
    return set(re.findall(r"\b([a-z][a-z0-9]{0,4})\s*\.", text.lower()))


def _job_pick_pred_col(aliases, idx):
    """Pick a JOB predicate column whose alias is in `aliases` (else fall back)."""
    allowed = [c for c in JOB_PRED_COLS if c.split(".")[0] in aliases]
    if not allowed:
        allowed = JOB_PRED_COLS
    return allowed[idx % len(allowed)]


def _job_col_alias(tok):
    """Alias of an `alias.col` token (None if not alias-qualified)."""
    return tok.split(".")[0] if "." in tok else None

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
    # NOTE: kind_type is a dimension of title (title.kind_id -> kind_type.id), so
    # it can only be joined where `title` is in scope. The join keys therefore
    # attach kt at the TOP of the tree (over the t.id=mi.movie_id join, whose left
    # input contains title) rather than inside the movie_info branch — joining
    # `kt ON t.kind_id=kt.id` inside that branch references `t` across the branch
    # boundary, which DuckDB rejects ("Non-inner join on correlated columns").
    ("jb_bushy6b", 5,
     "(((( title t {0} movie_keyword mk ON t.id = mk.movie_id) "
     "{1} keyword k ON mk.keyword_id = k.id) "
     "{2} ( movie_info mi {3} info_type it ON mi.info_type_id = it.id) "
     "ON t.id = mi.movie_id) "
     "{4} kind_type kt ON t.kind_id = kt.id)"),
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

    # Line (left-deep) topologies — a few for shape coverage
    for path_tables, path_conds in JOB_PATHS:
        aliases = {tt.split()[-1] for tt in path_tables}
        n_joins = len(path_conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[:SHAPE_LINE_VECS]):
            pred_col = _job_pick_pred_col(aliases, idx + vi)
            n_tables = len(path_tables)
            label = f"jb_line{n_tables}_{idx:03d}_v{vi}"
            queries[label] = _build_line_query(
                path_tables, path_conds, vec, pred_col, idx + vi, select_cols="*")
            idx += 1

    # Right-deep versions (chain paths only — star right-deep would emit a
    # correlated/LATERAL join that DuckDB rejects)
    for path_tables, path_conds in JOB_PATHS[:15]:
        aliases_seq = [tt.split()[-1] for tt in path_tables]
        if not _is_chain(aliases_seq, path_conds, _job_col_alias):
            continue
        n_joins = len(path_conds)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[5:5 + SHAPE_RD_VECS]):
            pred_col = _job_pick_pred_col(set(aliases_seq), idx + vi)
            n_tables = len(path_tables)
            label = f"jb_rd{n_tables}_{idx:03d}_v{vi}"
            queries[label] = _build_right_deep_query(
                path_tables, path_conds, vec, pred_col, idx + vi, select_cols="*")
            idx += 1

    # Bushy topologies (DOMINANT shape)
    for topo_label, n_joins, template in JOB_BUSHY_TEMPLATES:
        topo_aliases = _job_aliases_in(template)
        vecs = bench_vectors(n_joins)
        for vi, vec in enumerate(vecs[:SHAPE_BUSHY_VECS]):
            pred_col = _job_pick_pred_col(topo_aliases, idx + vi)
            label = f"{topo_label}_v{vi}"
            queries[label] = _build_bushy_query(template, vec, pred_col, idx + vi)
            idx += 1

    # Aggregation variants — one aggregate per query (COUNT/SUM/MIN/MAX, no
    # AVG). Each base's group/measure/predicate columns are alias-qualified and
    # belong to tables in that base's path, so the query binds.
    agg_bases = [
        {"tables": ["title t", "cast_info ci", "name n"],
         "conds": ["t.id = ci.movie_id", "ci.person_id = n.id"],
         "group": "ci.role_id", "measure": "t.production_year", "pred_col": "ci.person_id"},
        {"tables": ["title t", "movie_companies mc", "company_name cn"],
         "conds": ["t.id = mc.movie_id", "mc.company_id = cn.id"],
         "group": "cn.country_code", "measure": "t.production_year", "pred_col": "mc.company_id"},
    ]
    for ai, agg in enumerate(_expand_agg_bases(agg_bases)):
        path_tables, path_conds = agg["tables"], agg["conds"]
        n_joins = len(path_conds)
        vecs = bench_vectors(n_joins)
        vec = vecs[(ai + 3) % len(vecs)]
        label = f"jb_agg{ai}"
        queries[label] = _build_line_query(path_tables, path_conds, vec, agg["pred_col"], idx,
                                           agg=agg)
        idx += 1

    return queries


# ============================================================================
# Bench output helpers
# ============================================================================
def filter_excluded_bench_queries(queries, outdir, prefix):
    """Return only benchmark queries retained by the empirical corpus policy."""
    return {
        label: sql
        for label, sql in queries.items()
        if not is_excluded_query(outdir, f"{prefix}_{label}.sql")
    }


def write_bench_queries(queries, outdir, prefix):
    """Write all bench queries as individual .sql files (wipes old ones first)."""
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.endswith(".sql"):
            os.remove(os.path.join(outdir, f))
    for label, sql in sorted(queries.items()):
        fname = f"{prefix}_{label}.sql"
        if is_excluded_query(outdir, fname):
            continue
        with open(os.path.join(outdir, fname), "w") as f:
            f.write(sql + "\n")
    return sum(
        not is_excluded_query(outdir, f"{prefix}_{label}.sql")
        for label in queries
    )


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
              "ANY_VALUE", "INITCAP", "AVG("]
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
    q = filter_excluded_bench_queries(gen_tpch_queries(), TPCH_DIR, "oy_th")
    n = write_bench_queries(q, TPCH_DIR, "oy_th")
    verify_bench_queries(q, "TPC-H")
    print(f"  tpch/: {n} files written")

def gen_bench_tpcds():
    q = filter_excluded_bench_queries(gen_tpcds_queries(), TPCDS_DIR, "oy_ds")
    n = write_bench_queries(q, TPCDS_DIR, "oy_ds")
    verify_bench_queries(q, "TPC-DS")
    print(f"  tpcds/: {n} files written")

def gen_bench_job():
    q = filter_excluded_bench_queries(gen_job_queries(), JOB_DIR, "oy_jb")
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
