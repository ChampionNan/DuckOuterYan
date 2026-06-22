# `auto_test/` — OuterYan Optimizer Test & Benchmark Suite

Automated correctness + performance testing for the **OuterYan** optimizer module.
All scripts auto-resolve the repo root; the binary defaults to `build/release/duckdb`
(`DUCKDB_BIN=` or `--bin` to override). **Always test on a RELEASE build.**

---

## File Layout

```
auto_test/
  configs.sh            unified configuration (sourced by all scripts)
  run_all.sh            one-command full deployment (build + data + experiment)
  build_db.sh           build all databases (graph, tpch, tpcds, job)
  gen_queries.py        query corpus generator (all families)
  experiment_onoff.sh   correctness + performance experiment (ON vs OFF)
  trace_outer_yan.sh    per-query optimizer pass debugger
  outerjoin_query/      the query corpus (*.sql files)
    graph/              54 pairs (108 files) — structural + predicate queries -> graph_db
    tpch/               111 outer-join queries                                -> tpch_db
    tpcds/              104 outer-join queries                                -> tpcds_db
    job/                193 outer-join queries                                -> job_db
  results/              output directory (git-ignored)
```

---

## Configuration — `configs.sh`

Single source of truth for all parameters. Sourced automatically by every script.
Override via environment or per-script CLI flags (`CLI > env > configs.sh`).

Key parameters:

| Variable | Default | Purpose |
|---|---|---|
| `DUCKDB_BIN` | `build/release/duckdb` | Path to duckdb binary |
| `GRAPH_DATASET` | `bitcoin` | SNAP graph for graph R1..R10 (bitcoin/epinions/google/wiki/dblp) |
| `TPCH_SF` | `50` | TPC-H scale factor |
| `TPCDS_SF` | `50` | TPC-DS scale factor |
| `OY_THREADS` | `8` | Thread count for performance timing |
| `OY_TIMEOUT_SECS` | `300` | Soft per-query timeout (seconds) |
| `KILL_AFTER` | `600` | Hard SIGKILL watchdog (seconds; 0=off) |
| `OY_MIN_SECS` | `0` | Minimum timing window per query (0=just OY_RUNS) |
| `OY_RUNS` | `5` | Minimum timed iterations per query |

---

## Building Databases — `build_db.sh`

```
USAGE: bash auto_test/build_db.sh [target...]
Targets: graph | tpch | tpcds | job | all  (default: all)
```

| DB | Source | Notes |
|---|---|---|
| `graph_db` | SNAP graph data (external) → R1..R10 + views R/S/T/K | `GRAPH_DATASET`: bitcoin (24K, default), epinions (509K), dblp (1M), google (5.1M), wiki (28.5M) |
| `tpch_db` | `CALL dbgen(sf=N)` | Auto-rebuilds binary with `BUILD_TPCH=1` if needed |
| `tpcds_db` | `CALL dsdgen(sf=N)` | Auto-rebuilds binary with `BUILD_TPCDS=1` if needed |
| `job_db` | Remote parquet via httpfs (`duckdb/duckdb-data` v1.0) | Auto-rebuilds binary with `BUILD_HTTPFS=1` if needed |

**Environment variables:**

| Variable | Default | Purpose |
|---|---|---|
| `GRAPH_DATASET` | `bitcoin` | Which SNAP graph for graph tables |
| `TPCH_SF` | `50` | TPC-H scale factor |
| `TPCDS_SF` | `50` | TPC-DS scale factor |
| `GRAPH_DATA_DIR` | `$REPO/graph_data` | SNAP data cache directory |
| `FORCE` | `0` | Set to 1 to rebuild existing DBs |

**Examples:**

```bash
# Build everything:
bash auto_test/build_db.sh

# Build only graph with wiki dataset (28.5M edges):
GRAPH_DATASET=wiki bash auto_test/build_db.sh graph

# Build only tpch at SF=10:
TPCH_SF=10 bash auto_test/build_db.sh tpch

# Rebuild job (re-download from GitHub):
FORCE=1 bash auto_test/build_db.sh job
```

---

## Query Generation — `gen_queries.py`

```
USAGE: python3 auto_test/gen_queries.py [target]
Targets: graph | pred | tpch | tpcds | job | bench | validate | all  (default: all)
```

| Target | Output | Description |
|---|---|---|
| `graph` / `pred` | `outerjoin_query/graph/` | 54 predicate-bearing pairs (6 shapes x 9 predicates) |
| `tpch` | `outerjoin_query/tpch/` | 111 TPC-H outer-join queries |
| `tpcds` | `outerjoin_query/tpcds/` | 104 TPC-DS outer-join queries |
| `job` | `outerjoin_query/job/` | 193 JOB/IMDb outer-join queries |
| `bench` | tpch + tpcds + job | All benchmark families |
| `validate` | (removes broken queries) | EXPLAIN-test against DBs |
| `all` | graph + bench | Everything |

Design invariants: every query has >= 2 outer joins, mixed join-type vectors (LEFT/RIGHT/FULL),
diverse topologies (line, right-deep, bushy, star, branch), deterministic (`random.seed(42)`),
no banned functions.

```bash
python3 auto_test/gen_queries.py all          # regenerate everything
python3 auto_test/gen_queries.py validate     # EXPLAIN-test, remove broken queries
```

---

## Performance Experiment — `experiment_onoff.sh`

Correctness-gates each query first (ON==OFF), then times OFF vs ON.

```
USAGE: bash auto_test/experiment_onoff.sh [options]
  -b, --bin PATH      duckdb binary (default: build/release/duckdb)
  -n, --runs N        minimum timed runs per query (default: from configs.sh)
      --min-secs S    minimum measurement window in seconds (default: 0)
  -t, --timeout S     soft per-query timeout (default: 300)
      --kill-after S  hard SIGKILL watchdog (default: 600; 0=off)
      --only FAMILY   query families to run:
                        graph | tpch | tpcds | job | bench | all
                        (bench = tpch+tpcds+job; default: all)
      --pattern GLOB  only run queries matching this glob
      --exclude GLOB  skip queries matching any '|'-separated glob
      --limit N       cap total number of queries (0 = no cap)
  -o, --out FILE      output file (default: results/experiment_onoff_<timestamp>.txt)
  -h, --help          show usage
```

**Examples:**

```bash
# Run all families with defaults:
bash auto_test/experiment_onoff.sh

# Only TPC-H family:
bash auto_test/experiment_onoff.sh --only tpch

# Graph family with wiki dataset (large scale):
GRAPH_DATASET=wiki bash auto_test/experiment_onoff.sh --only graph --min-secs 5

# Bench families (tpch+tpcds+job), skip bushy7 queries:
bash auto_test/experiment_onoff.sh --only bench --exclude 'jb_bushy7*'

# Quick correctness check (no timing window):
bash auto_test/experiment_onoff.sh --only all --runs 1 --min-secs 0
```

**Output format:** Three sections — (1) query catalog with correctness status, (2) timing table for correct queries, (3) summary statistics with mean speed-up grouped by reorder/no-reorder.

---

## Debugging — `trace_outer_yan.sh`

Dumps every optimizer pass for a single query (OT construction, simplification, SJ pairs, DP, etc.) against an **existing** database file (`graph_db` / `tpch_db` / `tpcds_db` / `job_db`). The script does **not** build a temp DB — you point it at the same DB the query was originally written for via `--db`.

> Requires the **debug** binary (`build/debug/duckdb`). The `DUCKDB_OYTRACE` hook is compiled out of release builds. Build it once with `make debug` (add `BUILD_TPCH=1 BUILD_TPCDS=1` if those tables are referenced).

```
USAGE: bash auto_test/trace_outer_yan.sh --db PATH [options] (fails | -q "SQL")
  --db PATH          (REQUIRED) existing DuckDB database file
  -q "SQL"           query to trace (use -q OR `fails`)
  fails              trace 5 known-failing R/S/T/K queries (needs views, see below)
  -b, --bin PATH     duckdb binary (default: build/debug/duckdb)
  -o, --out FILE     output file (default: results/oy_trace.txt)
  -d, --outdir DIR   output dir for `fails` mode (default: results/oy_traces/)
```

```bash
# Trace one query against graph_db
bash auto_test/trace_outer_yan.sh --db graph_db \
    -q "SELECT * FROM R1 LEFT JOIN R2 ON R1.dst=R2.src WHERE R1.src % 10 = 0;"

# Trace an existing .sql file against tpch_db, custom output
bash auto_test/trace_outer_yan.sh --db tpch_db \
    -q "$(cat outerjoin_query/tpch/some_query.sql)" \
    -o results/oy_traces/some_query.trace.txt

# `fails` mode — 5 preset queries use R/S/T/K view names; create them once on graph_db:
build/debug/duckdb graph_db -c "
  CREATE VIEW IF NOT EXISTS R AS SELECT * FROM R1;
  CREATE VIEW IF NOT EXISTS S AS SELECT * FROM R2;
  CREATE VIEW IF NOT EXISTS T AS SELECT * FROM R3;
  CREATE VIEW IF NOT EXISTS K AS SELECT * FROM R4;"
bash auto_test/trace_outer_yan.sh --db graph_db fails
```
---

## One-Command Deployment — `run_all.sh`

Clone the repo and run a single command to compile, build all databases, and execute the full experiment:

```bash
git clone <DuckYanOuter repo> && cd DuckYanOuter
bash auto_test/run_all.sh
```

This handles everything: compile DuckDB with extensions → build graph/tpch/tpcds/job databases → run the on/off experiment with dual-thread timing.

**Environment overrides (all optional):**

| Variable | Default | Purpose |
|---|---|---|
| `GRAPH_DATASET` | `bitcoin` | SNAP graph (bitcoin/epinions/google/wiki/dblp) |
| `TPCH_SF` | `50` | TPC-H scale factor |
| `TPCDS_SF` | `50` | TPC-DS scale factor |
| `OY_THREADS` | `72` | Multi-thread count |
| `OY_RUNS` | `10` | Timed iterations per config (median taken) |
| `JOBS` | `nproc` | Make parallelism |
| `SKIP_BUILD` | `0` | Set to 1 to skip compilation |
| `SKIP_DATA` | `0` | Set to 1 to skip database generation |

```bash
# Large-scale run with wiki graph + SF=100:
GRAPH_DATASET=wiki TPCH_SF=100 TPCDS_SF=100 bash auto_test/run_all.sh

# Skip build if binary already exists:
SKIP_BUILD=1 bash auto_test/run_all.sh --only tpch

# Pass any experiment_onoff.sh flags after the script:
bash auto_test/run_all.sh --only graph --pattern 'line_N3*'
```

---

## Complete Workflow (Manual Steps)

```bash
# ===== Step 1: Clone & Build =====
git clone <DuckYanOuter repo>
cd DuckYanOuter
BUILD_TPCH=1 BUILD_TPCDS=1 BUILD_HTTPFS=1 GEN=ninja make release

# ===== Step 2: Build all databases =====
# build_db.sh auto-detects missing extensions and triggers make release if needed.
# Queries are already included in the repo (outerjoin_query/), no generation needed.
bash auto_test/build_db.sh all
#   graph_db  — SNAP bitcoin (default), ~24K edges → R1..R10
#   tpch_db   — TPC-H SF=50 via CALL dbgen(sf=50)
#   tpcds_db  — TPC-DS SF=50 via CALL dsdgen(sf=50)
#   job_db    — IMDb 21 tables via httpfs read_parquet (remote, ~1.75GB)

# ===== Step 3: Run the full on/off experiment =====
bash auto_test/experiment_onoff.sh
#   Correctness check (outer_yan ON == OFF) + dual-thread timing
#   threads=1 + threads=72, median of 10 runs per config

# ===== Step 4: Check results =====
cat auto_test/results/experiment_onoff_*.txt | tail -10

# ===== (Optional) Debug a specific query =====
bash auto_test/trace_outer_yan.sh --db graph_db \
    -q "SELECT * FROM R1 LEFT JOIN R2 ON R1.dst=R2.src INNER JOIN R3 ON R2.dst=R3.src;"
```

**Customization via environment (or edit `configs.sh`):**

```bash
# Use wiki graph (28.5M edges) for larger scale:
GRAPH_DATASET=wiki bash auto_test/build_db.sh graph

# Scale TPC-H to SF=100:
TPCH_SF=100 bash auto_test/build_db.sh tpch

# Quick test with fewer iterations and smaller scope:
bash auto_test/experiment_onoff.sh --only graph --runs 3 --limit 5
```

Databases (`graph_db`, `tpch_db`, `tpcds_db`, `job_db`) and `results/` are git-ignored.
