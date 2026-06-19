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
| `tpch_db`   | `CALL dbgen(sf=$TPCH_SF)`   (default 0.01) | binary built `BUILD_TPCH=1` |
| `tpcds_db`  | `CALL dsdgen(sf=$TPCDS_SF)` (default 0.01) | binary built `BUILD_TPCDS=1` |
| `job_db`    | external IMDb csv (no built-in generator)  | pre-built; set `JOB_DB=` or place at `$REPO/job_db` |

`equiv_db`'s `R1..R10.csv` come from `data_generation.py`; the equivalence /
semijoin query corpus from `gen_queries.py`. The `tpch/`, `tpcds/`, and `job/`
families come from the **filtered SQLStorm v1.0** corpus (≥2 outer joins, ≤1
top-level aggregate, outermost ORDER BY stripped) staged under
`auto_test/query/` — see `query/README.md` if added later for filter rules.

### Corpus layout (single source of truth)

`experiment_onoff.sh` reads its corpus from `$OY_CORPUS` (defaulted in
`test_config.sh` to `auto_test/query/`). Both correctness and performance
families share the same files; each family runs against its own DB:

```
auto_test/query/
  equivalence/select_star/   18 structural matrix queries (SELECT *)   -> equiv_db
  tpch/                       49 SQLStorm tpch outer-join queries       -> tpch_db
  tpcds/                      49 SQLStorm tpcds outer-join queries      -> tpcds_db
  job/                       819 SQLStorm job  outer-join queries       -> job_db
```

The legacy `outerjoin_query/` corpus (handwritten + `gen_queries.py` output)
is still in the repo for `compare_equal_batch.sh` / `experiment_semijoin.sh`;
`experiment_onoff.sh` now points at `auto_test/query/` by default.

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
Per-query wall-clock cap: `EQUIV_TIMEOUT=300` (select/agg/pred; 5 min, `0`=off)
and `BENCH_TIMEOUT=900` (tpch/tpcds) — a stuck query is killed, not left hanging.
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
- whole optimizer OFF vs ON over the **same corpus** correctness checks.
  Each family ships against its own DB:
  `select/agg/pred → equiv_db`, `tpch → tpch_db`, `tpcds → tpcds_db`,
  `job → job_db` (IMDb DB must be supplied externally — when missing, the
  job family is skipped with a warning and the rest still runs).
```
    --only select|agg|pred|tpch|tpcds|job|equiv|bench|all   query families (default all)
                                          equiv = select+agg+pred,
                                          bench = tpch+tpcds+job
    -r,--rscale N    equiv rows/table (default 1000 — scale up freely on a big machine)
    TPCH_SF= TPCDS_SF= (env)  scale for the tpch/tpcds families (default 0.01)
    JOB_DB= (env)             path to a pre-built IMDb DuckDB file (default $REPO/job_db)
    -t,--timeout S   soft per-query timeout (default 300; via `timeout`)
    --kill-after S   HARD SIGKILL any duckdb query running > S sec (default 600;
                     0 = off) — the backstop when a deadlock ignores --timeout
    --exclude GLOB   skip labels matching any '|'-separated glob (prune slow shapes)
    --pattern GLOB    --limit N    -n,--runs N    --min-secs S (window)    -o,--out FILE
```
The corpus root is fixed in `test_config.sh` as
`OY_CORPUS=$REPO/auto_test/query` — no env override needed for normal runs.

```bash
# default scale (RSCALE=1000, TPCH_SF=TPCDS_SF=0.01) — runs straight from auto_test/query/
bash auto_test/experiment_onoff.sh                          # all families
bash auto_test/experiment_onoff.sh --only tpch              # one family
bash auto_test/experiment_onoff.sh --only bench             # tpch + tpcds + job
bash auto_test/experiment_onoff.sh --only job               # IMDb (needs JOB_DB)

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

# 4. performance — corpus + DB paths come from test_config.sh; no env needed
bash auto_test/experiment_onoff.sh                  # all (job skipped if no JOB_DB)
# or one family at a time:
bash auto_test/experiment_onoff.sh --only tpch
bash auto_test/experiment_onoff.sh --only tpcds
bash auto_test/experiment_onoff.sh --only job      # needs $JOB_DB pre-built
bash auto_test/experiment_semijoin.sh

# 5. debug a failing query
bash auto_test/trace_outer_yan.sh -q "SELECT ...;"
```

Outputs (repo root, git-ignored): `equiv_db` / `tpch_db` / `tpcds_db` / `job_db`,
`compare_equal_batch_results.txt`, `experiment_*_results.txt`, `oy_trace*`.
