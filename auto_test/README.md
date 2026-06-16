# `auto_test/` — OuterYan optimizer test & benchmark

Scripts for the **OuterYan** optimizer: **correctness** (ON-vs-OFF equivalence),
**performance** (timing), **debugging** (per-pass traces). Each script finds the
repo itself; the binary defaults to `build/release/duckdb` (`DUCKDB_BIN=` or
`--bin` to override). **Test on a RELEASE build** — debug is failure-debugging only.

---

## Data & databases

Each DB is built once, reused, git-ignored, and rebuilt only if missing.

| DB | built from | needs |
|---|---|---|
| `equiv_db`  | `test/.../outer_yan/data/R1..R10.csv` → tables `R1..R10` + views `R/S/T/K` | `data_generation.py` |
| `tpch_db`   | `CALL dbgen(sf=$TPCH_SF)`   (default 10) | binary built `BUILD_TPCH=1` |
| `tpcds_db`  | `CALL dsdgen(sf=$TPCDS_SF)` (default 10) | binary built `BUILD_TPCDS=1` |

`equiv_db`'s `R1..R10.csv` come from `data_generation.py`; the query corpus from
`gen_queries.py`.

The corpus under `outerjoin_query/` is the **single source of truth** — both
correctness (`compare_equal_batch.sh`) and performance (`experiment_onoff.sh`) run
the **same** files, each family against its own DB:
```
outerjoin_query/
  equivalence/select_star/   structural matrix (SELECT *)          -> equiv_db
  equivalence/aggregation/   COUNT/SUM … GROUP BY                   -> equiv_db
  equivalence/predicates/    shapes + WHERE value predicates        -> equiv_db
  tpch/                      TPC-H outer joins + _p* predicate vars  -> tpch_db
  tpcds/                     TPC-DS outer joins + _p* predicate vars -> tpcds_db
  semijoin/                  star schema, ~54 shapes (gen_semijoin) -> experiment_semijoin.sh
```
All WHERE predicates are VALUE predicates (no NULL tests). **One generator**,
`gen_queries.py`, produces every family; pick what to (re)generate with a target
argument (below). Hand-written TPC anchors (`th1..`/`ds1..`) are preserved.

```
data_generation.py    write R1..Rk chain CSVs (behind equiv_db + experiment_onoff)
    --k N            number of tables R1..Rk
    --total-ids N    ids/rows to generate (joins are per-id → size scales linearly)
    --seed N         RNG seed
    --output-dir D   directory to write R*.csv into
gen_queries.py [TARGET]    (re)generate the SQL corpus (default TARGET=all)
    equiv      equivalence/{select_star,aggregation,predicates}/  -> equiv_db
    pred       equivalence/predicates/ only
    tpch       tpch/   base FK trees + <anchor>_p* value-predicate variants
    tpcds      tpcds/  base FK trees + <anchor>_p* value-predicate variants
    bench      tpch + tpcds
    semijoin   semijoin/  star-schema corpus (experiment_semijoin.sh)
    all        equiv + tpch + tpcds + semijoin
```
```bash
python3 auto_test/data_generation.py --k 10 --total-ids 1000000 --seed 42 \
        --output-dir test/sql/optimizer/outer_yan/data
```

---

## Correctness — `compare_equal_batch.sh`

Runs each query twice (OuterYan ON vs OFF) and checks the result sets match.

**All suites**
```bash
bash auto_test/compare_equal_batch.sh all
```

**One suite** — `compare_equal_batch.sh [select|agg|pred|tpch|tpcds|equiv|bench]`
(`equiv`=select+agg+pred, `bench`=tpch+tpcds). Env: `TPCH_SF`/`TPCDS_SF` (scale,
default 10), `BENCH_MEM=6GB`, `BENCH_TMPCAP=20GB`, `BENCH_TIMEOUT=900`.
```bash
rm -f tpch_db* tpcds_db*; TPCH_SF=1 TPCDS_SF=1 bash auto_test/compare_equal_batch.sh bench
```

**Single query** — `compare_equal.sh <on.sql> <off.sql> [db]`
```bash
P=auto_test/outerjoin_query/equivalence/select_star/line_N4_allLEFT
bash auto_test/compare_equal.sh "$P.sql" "${P}_off.sql" equiv_db
```

---

## Performance

Gate on correctness first (a wrong ON result is never timed), then time OFF vs ON;
release binary only.

### `experiment_onoff.sh` 
- whole optimizer OFF vs ON over the **same corpus** correctness checks
  (select/agg → equiv_db, tpch → tpch_db, tpcds → tpcds_db)
```
    --only select|agg|pred|tpch|tpcds|equiv|bench|all   query families (default all)
    -r,--rscale N    equiv rows/table (default 1e6 — scale up freely on a big machine)
    TPCH_SF= TPCDS_SF= (env)  scale for the tpch/tpcds families (default 1)
    -t,--timeout S   soft per-query timeout (default 300; via `timeout`)
    --kill-after S   HARD SIGKILL any duckdb query running > S sec (default 300 =
                     5 min; 0 = off) — the backstop when a deadlock ignores --timeout
    --exclude GLOB   skip labels matching any '|'-separated glob (prune slow shapes)
    --pattern GLOB    --limit N    -n,--runs N    --min-secs S (window)    -o,--out FILE
```
```bash
# big machine — full corpus at large scale (heavy queries hard-killed after 10 min):
bash auto_test/experiment_onoff.sh --rscale 2000000 --kill-after 600
# small machine — prune the heavy fan-out shapes, default 5-min hard kill:
bash auto_test/experiment_onoff.sh --rscale 100000 --exclude 'bushy*_N[56]_*|branch_N[56]_*|chain_N*'
```
Output: `experiment_onoff_results.txt`

### `experiment_semijoin.sh` 
- OuterYan SJ filters vs DuckDB SEMI over a star schema (fact + d1/d2/d3).
  **Section A:** the ~54-query corpus `outerjoin_query/semijoin/`, each gated
  ON==OFF then timed BASELINE/BITMAP/HASH. **Section B:** the `dim ⟕ fact`
  skeleton across a selectivity sweep (adds the DUCKDB_SEMI rewrite).
```
    -N fact rows   -D key domain   -p dim selectivity (Sec A)   -n runs
    -t timeout   --kill-after S (hard SIGKILL > S sec, default 300)   --tpch SF   -o,--out FILE
```
```bash
bash auto_test/experiment_semijoin.sh -N 1000000 -D 200000 -p 0.5
```
Output: `experiment_semijoin_results.txt`

---

## Debugging — `trace_outer_yan.sh`

Dumps every optimizer pass for a query, so you can see which rule rewrote which
edge. Flow:
```
input plan → BuildOT → Simplify → SJ pairs → Desimplify → DP → Resimplify
           → SJ insertion → (aggregate) agg pushdown
```
```
    -q "SELECT … ;"   trace one query        fails   trace the known-failing bundle
    -b,--bin PATH     -o,--out FILE (default oy_trace.txt)   -d,--outdir DIR (default oy_traces/)
```
```bash
bash auto_test/trace_outer_yan.sh -q "SELECT * FROM R LEFT JOIN S ON R.dst=S.src;"
```

---

## Whole testing flow

```bash
# 1. generate R1..R10 data (for equiv_db + onoff)
python3 auto_test/data_generation.py --k 10 --total-ids 1000000 --seed 42 \
        --output-dir test/sql/optimizer/outer_yan/data

# 2. build a release binary WITH the tpch/tpcds extensions
BUILD_TPCH=1 BUILD_TPCDS=1 GEN=ninja make release
export DUCKDB_BIN="$PWD/build/release/duckdb"

# 3. correctness (all suites) -> file, then list failures
bash auto_test/compare_equal_batch.sh all > compare_equal_batch_results.txt 2>&1
grep -E '❌ FAIL|⚠️' compare_equal_batch_results.txt

# 4. performance
bash auto_test/experiment_onoff.sh --rscale 100000
bash auto_test/experiment_semijoin.sh

# 5. debug a failing query
bash auto_test/trace_outer_yan.sh -q "SELECT ...;"
```

Outputs (repo root, git-ignored): `equiv_db` / `tpch_db` / `tpcds_db`,
`compare_equal_batch_results.txt`, `experiment_*_results.txt`, `oy_trace*`.
