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

```
data_generation.py    write R1..Rk chain CSVs (behind equiv_db + experiment_onoff)
    --k N            number of tables R1..Rk
    --total-ids N    ids/rows to generate (joins are per-id → size scales linearly)
    --seed N         RNG seed
    --output-dir D   directory to write R*.csv into
gen_queries.py [equiv|tpch|tpcds|bench|all]   (re)generate the SQL corpus
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

**One suite** — `compare_equal_batch.sh [select|agg|tpch|tpcds|equiv|bench]`
(`equiv`=select+agg, `bench`=tpch+tpcds). Env: `TPCH_SF`/`TPCDS_SF` (scale,
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
- whole optimizer OFF vs ON over the equivalence corpus
```
    -r,--rscale N    rows/table (default 1e6; use ~1e5 so heavy branch/bushy
                     queries don't blow the gate timeout)
    --only select|agg|all    --pattern GLOB    --limit N
    -n,--runs N    --min-secs S (timing window)    -t,--timeout S    -o,--out FILE
```
```bash
bash auto_test/experiment_onoff.sh --rscale 100000 -t 120
```
Output: `experiment_onoff_results.txt`

### `experiment_semijoin.sh` 
- OuterYan SJ filters vs DuckDB SEMI (`dim ⋈ fact`)
```
    -N fact rows    -D key domain    -n runs    -t timeout    -b,--bin PATH    -o,--out FILE
```
```bash
bash auto_test/experiment_semijoin.sh -N 1000000 -D 200000
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
