#!/bin/bash
# ============================================================================
# compare_equal_batch.sh  —  OuterYan OFF-vs-ON correctness suite (file-based).
#
# Every test is a .sql FILE PAIR run through compare_equal.sh, which loads each
# side's result as a table and diffs them with EXCEPT both ways (set-based,
# order-independent). For OuterYan we pair, per query:
#
#   <q>.sql       the bare query              -> OuterYan ON  (default)
#   <q>_off.sql   SET disabled_optimizers     -> OuterYan OFF (oracle)
#                 TO 'outer_yan'; <same query>
#
# Suites (each self-builds its database once, then runs every pair in a dir):
#   select   equivalence/select_star/  structural matrix N=3..6 + deep chains
#   agg      equivalence/aggregation/  COUNT/SUM … GROUP BY            } equiv DB
#   tpch     tpch/                     real TPC-H schema (dbgen sf=10; TPCH_SF= to override)
#   tpcds    tpcds/                    real TPC-DS schema (dsdgen sf=10; TPCDS_SF= to override)
#
# USAGE: compare_equal_batch.sh [select|agg|tpch|tpcds|equiv|bench|all]
#   select / 1   equivalence: SELECT *          (equiv DB)
#   agg    / 2   equivalence: aggregation       (equiv DB)
#   tpch   / 3   TPC-H outer-join families      (tpch DB; needs dbgen)
#   tpcds  / 4   TPC-DS outer-join families     (tpcds DB; needs dsdgen)
#   equiv        select + agg
#   bench        tpch + tpcds
#   all (default) all four
#
# Build a RELEASE duckdb for runs (DUCKDB_BIN= or build/release/duckdb); the
# debug binary is the fallback and is for failure-debugging only.
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DUCKDB_BIN="${DUCKDB_BIN:-$REPO_ROOT/build/release/duckdb}"
[ -x "$DUCKDB_BIN" ] || DUCKDB_BIN="$REPO_ROOT/build/debug/duckdb"
export DUCKDB_BIN

EQUIV_DB="${EQUIV_DB:-$REPO_ROOT/equiv_db}"
TPCH_DB="${TPCH_DB:-$REPO_ROOT/tpch_db}";   TPCH_SF="${TPCH_SF:-10}"
TPCDS_DB="${TPCDS_DB:-$REPO_ROOT/tpcds_db}"; TPCDS_SF="${TPCDS_SF:-10}"

# Per-query wall-clock cap for the equivalence (compare_equal.sh) suites; the
# bench suites have their own BENCH_TIMEOUT. Default 5 min; EQUIV_TIMEOUT=0 = off.
EQUIV_TIMEOUT="${EQUIV_TIMEOUT:-300}"
TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"   # GNU coreutils; '' on bare macOS

# Helper: run one ON/OFF pair through compare_equal.sh against ${DB} and verdict.
# The compare_equal.sh call is wrapped in `timeout` (SIGKILL EQUIV_TIMEOUT+5s after)
# so a stuck query is capped at 5 min instead of hanging the whole suite.
compare_pair() {
    local file1=$1 file2=$2
    [ -f "$file1" ] || { echo "⚠️  MISSING: $file1"; return; }
    [ -f "$file2" ] || { echo "⚠️  MISSING: $file2"; return; }
    local db="${DB:-$EQUIV_DB}" result rc
    if [ -n "$TIMEOUT_BIN" ] && [ "${EQUIV_TIMEOUT:-0}" -gt 0 ]; then
        result=$("$TIMEOUT_BIN" -k 5 "$EQUIV_TIMEOUT" "$SCRIPT_DIR/compare_equal.sh" "$file1" "$file2" "$db"); rc=$?
    else
        result=$("$SCRIPT_DIR/compare_equal.sh" "$file1" "$file2" "$db"); rc=$?
    fi
    if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then          # 124=timed out, 137=SIGKILL (-k)
        echo "⏱️  TIMEOUT(${EQUIV_TIMEOUT}s): $(basename "$file1")"
    elif echo "$result" | grep -q "SUCCESS"; then
        echo "✅ PASS: $(basename "$file1")"
    else
        echo "❌ FAIL: $(basename "$file1")"
        echo "   (Run '$SCRIPT_DIR/compare_equal.sh $file1 $file2 $db' to see the diff)"
    fi
}

# Compare every <q>.sql (OuterYan ON) against its <q>_off.sql (OFF) in a dir.
run_equiv_dir() {  # $1=dir $2=db
    local DB="$2" on off
    for on in "$1"/*.sql; do
        case "$on" in *_off.sql) continue;; esac
        off="${on%.sql}_off.sql"
        compare_pair "$on" "$off"
    done
}

# --- disk-safe in-engine comparison (for large bench results) ----------------
# The compare_equal.sh path materialises each side's FULL result to a CSV, which
# explodes on real TPC-H/DS data (a single sf=1 SELECT * over lineitem can be
# 20+ GB). compare_pair_inengine instead runs BOTH sides as TEMP tables inside ONE
# duckdb process and counts the symmetric set-difference + row-count delta — no
# result ever hits the disk as CSV. memory_limit + max_temp_directory_size CAP the
# spill, so a runaway (fan-out) query ERRORs cleanly instead of filling the disk.
BENCH_MEM="${BENCH_MEM:-100GB}"
BENCH_TMPCAP="${BENCH_TMPCAP:-50GB}"
BENCH_TIMEOUT="${BENCH_TIMEOUT:-900}"
compare_pair_inengine() {  # $1=on.sql $2=db
    local on="$1" db="$2" q label out diff tmo
    label="$(basename "$on" .sql)"
    [ -f "$on" ] || { echo "⚠️  MISSING: $on"; return; }
    q="$(sed 's/;[[:space:]]*$//' "$on")"             # bare query, trailing ; stripped
    tmo="$(command -v timeout || command -v gtimeout || true)"
    out="$( { [ -n "$tmo" ] && set -- "$tmo" "$BENCH_TIMEOUT" "$DUCKDB_BIN" "$db" -noheader -list \
                            || set -- "$DUCKDB_BIN" "$db" -noheader -list
        "$@" <<SQL 2>&1
PRAGMA memory_limit='$BENCH_MEM';
SET max_temp_directory_size='$BENCH_TMPCAP';
SET disabled_optimizers TO 'outer_yan';
CREATE TEMP TABLE _off AS $q;
SET disabled_optimizers TO '';
CREATE TEMP TABLE _on AS $q;
SELECT (SELECT count(*) FROM (SELECT * FROM _off EXCEPT SELECT * FROM _on))
     + (SELECT count(*) FROM (SELECT * FROM _on EXCEPT SELECT * FROM _off))
     + abs((SELECT count(*) FROM _off) - (SELECT count(*) FROM _on)) AS diff;
SQL
    } )"
    if [ -z "$out" ]; then
        echo "⏱️  TIMEOUT(${BENCH_TIMEOUT}s) or empty: $label"
    elif printf '%s' "$out" | grep -qiE 'error|exceed|out of memory|temp'; then
        echo "⚠️  ERROR: $label"; printf '%s' "$out" | grep -iE 'error|exceed|out of memory|temp' | head -1 | sed 's/^/        /'
    else
        diff="$(printf '%s' "$out" | grep -oE '^-?[0-9]+$' | tail -1)"
        if [ "$diff" = "0" ]; then echo "✅ PASS: $label"
        else echo "❌ FAIL: $label (symdiff+rowdelta=${diff:-?})"; fi
    fi
}

run_bench_dir() {  # $1=dir $2=db ; disk-safe in-engine comparison
    local on
    for on in "$1"/*.sql; do
        case "$on" in *_off.sql) continue;; esac
        compare_pair_inengine "$on" "$2"
    done
}

# --- database builders (each built once, reused; git-ignored) ----------------
build_equiv_db() {  # R1..R10 tables + R/S/T/K views from the chain CSVs
    [ -f "$EQUIV_DB" ] && return 0
    local D="$REPO_ROOT/test/sql/optimizer/outer_yan/data"
    shopt -s nullglob; local csvs=("$D"/R*.csv); shopt -u nullglob
    [ ${#csvs[@]} -gt 0 ] || { echo "Error: no R*.csv under $D" >&2; return 1; }
    echo "Building equiv DB ($EQUIV_DB) from ${#csvs[@]} tables ..."
    { local c t
      for c in "${csvs[@]}"; do t="$(basename "$c" .csv)"
        echo "CREATE TABLE $t AS SELECT * FROM read_csv('$c', header=false, columns={'src':'BIGINT','dst':'BIGINT'});"
      done
      echo "CREATE VIEW R AS SELECT * FROM R1; CREATE VIEW S AS SELECT * FROM R2;"
      echo "CREATE VIEW T AS SELECT * FROM R3; CREATE VIEW K AS SELECT * FROM R4;"
    } | "$DUCKDB_BIN" "$EQUIV_DB" >/dev/null || { echo "Error: failed to build equiv DB" >&2; return 1; }
}

build_tpch_db() {  # full TPC-H schema via the dbgen extension
    [ -f "$TPCH_DB" ] && return 0
    echo "Building TPC-H DB ($TPCH_DB, sf=$TPCH_SF) ..."
    "$DUCKDB_BIN" "$TPCH_DB" -c "CALL dbgen(sf=$TPCH_SF);" >/dev/null 2>&1 \
        || { echo "⚠️  SKIP TPC-H: dbgen not available in $DUCKDB_BIN"; rm -f "$TPCH_DB" "$TPCH_DB".wal; return 1; }
}

build_tpcds_db() {  # full TPC-DS schema via the dsdgen extension
    [ -f "$TPCDS_DB" ] && return 0
    echo "Building TPC-DS DB ($TPCDS_DB, sf=$TPCDS_SF) ..."
    "$DUCKDB_BIN" "$TPCDS_DB" -c "CALL dsdgen(sf=$TPCDS_SF);" >/dev/null 2>&1 \
        || { echo "⚠️  SKIP TPC-DS: dsdgen not available in $DUCKDB_BIN"; rm -f "$TPCDS_DB" "$TPCDS_DB".wal; return 1; }
}

# --- suites ------------------------------------------------------------------
test_equality_select() {
    echo "---- OuterYan equivalence: SELECT * (ON vs OFF) ----"
    build_equiv_db || return
    run_equiv_dir "$SCRIPT_DIR/outerjoin_query/equivalence/select_star" "$EQUIV_DB"
}
test_equality_agg() {
    echo "---- OuterYan equivalence: aggregation (ON vs OFF) ----"
    build_equiv_db || return
    run_equiv_dir "$SCRIPT_DIR/outerjoin_query/equivalence/aggregation" "$EQUIV_DB"
}
test_equality_pred() {
    echo "---- OuterYan equivalence: predicates (ON vs OFF) ----"
    build_equiv_db || return
    run_equiv_dir "$SCRIPT_DIR/outerjoin_query/equivalence/predicates" "$EQUIV_DB"
}
test_equality_tpch() {
    echo "---- OuterYan equivalence: TPC-H (ON vs OFF, in-engine sf=$TPCH_SF) ----"
    build_tpch_db || return
    run_equiv_dir "$SCRIPT_DIR/outerjoin_query/tpch" "$TPCH_DB"
}
test_equality_tpcds() {
    echo "---- OuterYan equivalence: TPC-DS (ON vs OFF, in-engine sf=$TPCDS_SF) ----"
    build_tpcds_db || return
    run_equiv_dir "$SCRIPT_DIR/outerjoin_query/tpcds" "$TPCDS_DB"
}

# --- dispatch ----------------------------------------------------------------
TEST_NUM=${1:-all}
echo "========================================"
echo "OuterYan OFF-vs-ON correctness suite"
echo "  binary : $DUCKDB_BIN"
echo "  suite  : $TEST_NUM"
echo "========================================"

case $TEST_NUM in
    select|1)  test_equality_select ;;
    agg|2)     test_equality_agg ;;
    pred|3)    test_equality_pred ;;
    tpch|4)    test_equality_tpch ;;
    tpcds|5)   test_equality_tpcds ;;
    equiv)     test_equality_select; test_equality_agg; test_equality_pred ;;
    bench)     test_equality_tpch; test_equality_tpcds ;;
    all)       test_equality_select; test_equality_agg; test_equality_pred
               test_equality_tpch;   test_equality_tpcds ;;
    *)
        echo "Usage: $0 [select|agg|pred|tpch|tpcds|equiv|bench|all]"
        echo "  select / 1   equivalence: SELECT *        (equiv DB)"
        echo "  agg    / 2   equivalence: aggregation     (equiv DB)"
        echo "  pred   / 3   equivalence: WHERE predicates(equiv DB)"
        echo "  tpch   / 4   TPC-H outer-join families    (needs dbgen)"
        echo "  tpcds  / 5   TPC-DS outer-join families   (needs dsdgen)"
        echo "  equiv        select + agg + pred"
        echo "  bench        tpch + tpcds"
        echo "  all (default) everything"
        exit 1 ;;
esac

echo "========================================"
echo "Test Suite Complete"
echo "========================================"
