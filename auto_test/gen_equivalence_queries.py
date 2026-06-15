#!/usr/bin/env python3
# ============================================================================
# gen_equivalence_queries.py
#
# Writes the OuterYan OFF-vs-ON equivalence corpus as .sql FILE PAIRS under
# auto_test/outerjoin_query/equivalence/, in the compare_equal.sh / _batch.sh
# convention (compare_equal_batch.sh test_equality runs each pair):
#
#   <label>.sql       the bare query              -> OuterYan ON  (default)
#   <label>_off.sql   SET disabled_optimizers     -> OuterYan OFF (oracle)
#                     TO 'outer_yan'; <same query>
#
# Two subdirectories, separated by query kind:
#   equivalence/select_star/  : SELECT * queries —
#        full structural matrix N=3..6 × {line,star,bushy} × kind vectors (126)
#        + deep chains (7- and 10-relation, R1..R10)
#   equivalence/aggregation/  : COUNT/SUM … GROUP BY over R/S/T/K (5)
# All run against the self-contained equiv DB (R1..R10 + R/S/T/K; R/S/T/K =
# R1..R4, and R1..R6 cover the matrix). Re-run to regenerate.
# ============================================================================
import os

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "outerjoin_query", "equivalence")
SELECT_DIR = os.path.join(BASE, "select_star")
AGG_DIR = os.path.join(BASE, "aggregation")
OFF_PREFIX = "SET disabled_optimizers TO 'outer_yan';\n"

KIND = {"INNER": "INNER JOIN", "LEFT": "LEFT OUTER JOIN",
        "RIGHT": "RIGHT OUTER JOIN", "FULL": "FULL OUTER JOIN"}

# --- structural matrix (same builder as compare_outer_yan.sh) ----------------
def vectors(e):
    cyc = lambda seq: [seq[i % 4] for i in range(e)]
    return {"allINNER": ["INNER"]*e, "allLEFT": ["LEFT"]*e, "allRIGHT": ["RIGHT"]*e,
            "allFULL": ["FULL"]*e,
            "mixA": cyc(["LEFT","INNER","RIGHT","FULL"]),
            "mixB": cyc(["FULL","RIGHT","INNER","LEFT"]),
            "mixC": cyc(["RIGHT","FULL","LEFT","INNER"])}
def lf(i): return {"sql": f"R{i}", "rels": [i]}
def jn(A, B, kind, a, b):
    return {"sql": f"({A['sql']} {KIND[kind]} {B['sql']} ON R{a}.dst=R{b}.src)",
            "rels": A["rels"] + B["rels"]}
def sel(t): return "SELECT * FROM " + t["sql"]
def shapes_for(n, k):
    S = {}
    t = lf(1)
    for i in range(2, n+1): t = jn(t, lf(i), k[i-2], i-1, i)
    S["line"] = sel(t)
    t = lf(1)
    for i in range(2, n+1): t = jn(t, lf(i), k[i-2], 1, i)
    S["star"] = sel(t)
    if n == 3:
        S["bushyR"] = sel(jn(lf(1), jn(lf(2), lf(3), k[1], 2, 3), k[0], 1, 2))
    elif n == 4:
        S["bushyBal"]  = sel(jn(jn(lf(1),lf(2),k[0],1,2), jn(lf(3),lf(4),k[2],3,4), k[1], 2, 3))
        S["bushyBal2"] = sel(jn(jn(lf(1),lf(2),k[0],1,2), jn(lf(3),lf(4),k[2],3,4), k[1], 1, 3))
        S["branchY"]   = sel(jn(jn(lf(1), jn(lf(2),lf(3),k[1],2,3), k[0],1,2), lf(4), k[2], 2, 4))
    elif n == 5:
        S["bushyBal"] = sel(jn(jn(jn(lf(1),lf(2),k[0],1,2), lf(3),k[1],2,3),
                               jn(lf(4),lf(5),k[3],4,5), k[2], 3, 4))
        S["bushyR"]   = sel(jn(lf(1), jn(lf(2), jn(lf(3), jn(lf(4),lf(5),k[3],4,5), k[2],3,4),
                               k[1],2,3), k[0], 1, 2))
        S["branch"]   = sel(jn(jn(lf(1),lf(2),k[0],1,2),
                               jn(jn(lf(3),lf(4),k[2],3,4), lf(5),k[3],3,5), k[1], 2, 3))
    elif n == 6:
        S["bushyBal"] = sel(jn(jn(jn(lf(1),lf(2),k[0],1,2), lf(3),k[1],2,3),
                               jn(jn(lf(4),lf(5),k[3],4,5), lf(6),k[4],5,6), k[2], 3, 4))
        S["bushy2"]   = sel(jn(jn(lf(1), jn(lf(2),lf(3),k[1],2,3), k[0],1,2),
                               jn(lf(4), jn(lf(5),lf(6),k[4],5,6), k[3],4,5), k[2], 3, 4))
        S["branch"]   = sel(jn(jn(jn(lf(1),lf(2),k[0],1,2), jn(lf(3),lf(4),k[2],3,4), k[1],2,3),
                               jn(lf(5),lf(6),k[4],5,6), k[3], 2, 5))
    return S

def matrix_queries():
    out = {}
    for n in range(3, 7):
        vs = vectors(n - 1)
        for sname in shapes_for(n, vs["allINNER"]):
            for vname, k in vs.items():
                out[f"{sname}_N{n}_{vname}"] = shapes_for(n, k)[sname] + ";"
    return out

# --- aggregate + deep chains over R/S/T/K and R1..R10 ------------------------
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

def write_pair(outdir, label, sql):
    with open(os.path.join(outdir, f"{label}.sql"), "w") as f:
        f.write(sql + "\n")
    with open(os.path.join(outdir, f"{label}_off.sql"), "w") as f:
        f.write(OFF_PREFIX + sql + "\n")

def main():
    for d in (SELECT_DIR, AGG_DIR):
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):                       # wipe any previous generation
            if f.endswith(".sql"):
                os.remove(os.path.join(d, f))
    # SELECT * corpus -> select_star/  ;  aggregate corpus -> aggregation/
    sel = dict(matrix_queries())
    agg = {}
    for label, sql in extra_queries().items():
        (agg if label.startswith("agg_") else sel)[label] = sql
    for label, sql in sel.items():
        write_pair(SELECT_DIR, label, sql)
    for label, sql in agg.items():
        write_pair(AGG_DIR, label, sql)
    print(f"select_star/: {len(sel)} pairs ; aggregation/: {len(agg)} pairs "
          f"({2*(len(sel)+len(agg))} files total)")

if __name__ == "__main__":
    main()
