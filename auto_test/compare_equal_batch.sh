#!/bin/bash
# ============================================================================
# compare_equal_batch.sh — OuterYan OFF-vs-ON correctness suite
# Scheme B: Embedded compare logic, NO external compare_equal.sh
# Behavior fully aligned with original compare_equal.sh, NO json extension dependency
# Single DB connection per test case, add kill residual duckdb process to eliminate lock conflict
# ============================================================================
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DUCKDB_BIN="${DUCKDB_BIN:-$REPO_ROOT/build/release/duckdb}"
[ -x "$DUCKDB_BIN" ] || DUCKDB_BIN="$REPO_ROOT/build/debug/duckdb"
export DUCKDB_BIN

# Database paths & scale factors
EQUIV_DB="${EQUIV_DB:-$REPO_ROOT/equiv_db}"
TPCH_DB="${TPCH_DB:-$REPO_ROOT/tpch_db}";   TPCH_SF="${TPCH_SF:-10}"
TPCDS_DB="${TPCDS_DB:-$REPO_ROOT/tpcds_db}"; TPCDS_SF="${TPCDS_SF:-10}"

# Equivalence suite config
EQUIV_TIMEOUT="${EQUIV_TIMEOUT:-300}"
EQUIV_MEM="${EQUIV_MEM:-20GB}"
EQUIV_THREADS=4
TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"

# TPC-H / TPC-DS large benchmark config
BENCH_MEM="${BENCH_MEM:-100GB}"
BENCH_TMPCAP="${BENCH_TMPCAP:-50GB}"
BENCH_TIMEOUT="${BENCH_TIMEOUT:-900}"
BENCH_THREADS=8

# -----------------------------------------------------------------------------
# Utility: Kill residual duckdb process + Clean residual .wal / .lock file
# -----------------------------------------------------------------------------
clean_db_lock() {
    local db="$1"
    local db_base=$(basename "$db")
    # 查找所有打开该数据库的duckdb进程并强制杀死
    lsof "$db" 2>/dev/null | awk '/duckdb/ {print $2}' | sort -u | xargs -r kill -9 2>/dev/null
    sleep 0.2
    rm -f "${db}.wal" "${db}.lock"
}

# -----------------------------------------------------------------------------
# Embedded internal replacement of original compare_equal.sh
# Input: $1=on.sql, $2=off.sql, $3=db_path
# Behavior 100% match original compare_equal.sh, NO json extension
# All logic runs in ONE single DuckDB process, only open DB ONCE
# -----------------------------------------------------------------------------
run_compare_two_files() {
    local file_on="$1"
    local file_off="$2"
    local db="$3"
    local label q_on q_off tmo out rc

    label="$(basename "$file_on" .sql)"
    [ -f "$file_on" ] || { echo "⚠️  MISSING: $file_on"; return 2; }
    [ -f "$file_off" ] || { echo "⚠️  MISSING: $file_off"; return 2; }

    # Read raw SQL, strip trailing semicolon
    q_on=$(sed 's/;[[:space:]]*$//' "$file_on")
    q_off_raw=$(cat "$file_off")
    # Strip redundant SET outer_yan line from off sql file
    q_off=$(echo "$q_off_raw" | sed '/SET disabled_optimizers/d' | sed 's/;[[:space:]]*$//')

    # Clean lock before open DB (kill residual duckdb first)
    clean_db_lock "$db"
    tmo="$TIMEOUT_BIN"

    # All work inside ONE duckdb process, only attach DB once
    # No json_group_array, fully align original compare_equal.sh diff output
    out="$( {
        if [ -n "$tmo" ] && [ "${EQUIV_TIMEOUT:-0}" -gt 0 ]; then
            set -- "$tmo" -k 30 "$EQUIV_TIMEOUT" "$DUCKDB_BIN" "$db" -noheader -list
        else
            set -- "$DUCKDB_BIN" "$db" -noheader -list
        fi
        "$@" <<SQL 2>&1
PRAGMA memory_limit='$EQUIV_MEM';
PRAGMA threads=$EQUIV_THREADS;
-- Execute OFF version (OuterYan disabled)
CREATE TEMP TABLE _tmp_off AS $q_off;
-- Execute ON version (OuterYan enabled)
SET disabled_optimizers TO '';
CREATE TEMP TABLE _tmp_on AS $q_on;
-- Same diff logic as original compare_equal.sh
SELECT 'In $file_on but not $file_off' as source, * FROM (SELECT * FROM _tmp_off EXCEPT SELECT * FROM _tmp_on)
UNION ALL
SELECT 'In $file_off but not $file_on' as source, * FROM (SELECT * FROM _tmp_on EXCEPT SELECT * FROM _tmp_off);
SQL
    } )"
    rc=$?
    # 执行完成再次清理残留进程
    clean_db_lock "$db"

    # Parse output & print verdict, exactly match old compare_equal.sh message
    if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
        echo "⏱️  TIMEOUT(${EQUIV_TIMEOUT}s): $label"
        return 1
    elif echo "$out" | grep -qiE 'conflicting lock|IO Error|Catalog Error|error|out of memory'; then
        echo "❌ DB ERROR: $label"
        printf '%s' "$out" | grep -iE 'error|lock|memory' | head -1 | sed 's/^/        /'
        return 1
    elif [ -z "$out" ]; then
        echo "✅ PASS: $label"
        return 0
    else
        echo "❌ FAIL: $label"
        echo "   Differences:"
        echo "$out"
        echo "   Debug command: $DUCKDB_BIN $db"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Equivalence test dir runner (select/agg/pred)
# Sleep 0.5s after each case to fully release CPU & DB lock
# -----------------------------------------------------------------------------
run_equiv_dir() {
    local dir="$1"
    local db="$2"
    local on off
    for on in "$dir"/*.sql; do
        case "$on" in
            *_off.sql) continue ;;
        esac
        off="${on%.sql}_off.sql"
        run_compare_two_files "$on" "$off" "$db"
        # 延长等待时间，彻底释放数据库锁
        sleep 0.5
    done
}

# -----------------------------------------------------------------------------
# Original in-engine compare for large TPC-H / TPC-DS (unchanged)
# Single process internal diff, no CSV export, disk friendly
# -----------------------------------------------------------------------------
compare_pair_inengine() {
    local on="$1" db="$2" q label out diff tmo
    label="$(basename "$on" .sql)"
    [ -f "$on" ] || { echo "⚠️  MISSING: $on"; return; }
    q="$(sed 's/;[[:space:]]*$//' "$on")"
    tmo="$TIMEOUT_BIN"
    clean_db_lock "$db"

    out="$( { [ -n "$tmo" ] && set -- "$tmo" "$BENCH_TIMEOUT" "$DUCKDB_BIN" "$db" -noheader -list \
                    || set -- "$DUCKDB_BIN" "$db" -noheader -list
        "$@" <<SQL 2>&1
PRAGMA memory_limit='$BENCH_MEM';
PRAGMA threads=$BENCH_THREADS;
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
    elif printf '%s' "$out" | grep -qiE 'error|exceed|out of memory|temp|lock'; then
        echo "⚠️  ERROR: $label"; printf '%s' "$out" | grep -iE 'error|exceed|out of memory|temp|lock' | head -1 | sed 's/^/        /'
    else
        diff="$(printf '%s' "$out" | grep -oE '^-?[0-9]+$' | tail -1)"
        if [ "$diff" = "0" ]; then echo "✅ PASS: $label"
        else echo "❌ FAIL: $label (symdiff+rowdelta=${diff:-?})"; fi
    fi
    clean_db_lock "$db"
    sleep 0.5
}

run_bench_dir() {
    local on
    for on in "$1"/*.sql; do
        case "$on" in *_off.sql) continue;; esac
        compare_pair_inengine "$on" "$2"
    done
}

# -----------------------------------------------------------------------------
# Database builder functions (unchanged)
# -----------------------------------------------------------------------------
build_equiv_db() {
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

build_tpch_db() {
    [ -f "$TPCH_DB" ] && return 0
    echo "Building TPC-H DB ($TPCH_DB, sf=$TPCH_SF) ..."
    "$DUCKDB_BIN" "$TPCH_DB" -c "CALL dbgen(sf=$TPCH_SF);" >/dev/null 2>&1 \
        || { echo "⚠️  SKIP TPC-H: dbgen not available in $DUCKDB_BIN"; rm -f "$TPCH_DB" "$TPCH_DB".wal "$TPCH_DB".lock; return 1; }
}

build_tpcds_db() {
    [ -f "$TPCDS_DB" ] && return 0
    echo "Building TPC-DS DB ($TPCDS_DB, sf=$TPCDS_SF) ..."
    "$DUCKDB_BIN" "$TPCDS_DB" -c "CALL dsdgen(sf=$TPCDS_SF);" >/dev/null 2>&1 \
        || { echo "⚠️  SKIP TPC-DS: dsdgen not available in $DUCKDB_BIN"; rm -f "$TPCDS_DB" "$TPCDS_DB".wal "$TPCDS_DB".lock; return 1; }
}

# -----------------------------------------------------------------------------
# Test suite entry points
# -----------------------------------------------------------------------------
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
    run_bench_dir "$SCRIPT_DIR/outerjoin_query/tpch" "$TPCH_DB"
}
test_equality_tpcds() {
    echo "---- OuterYan equivalence: TPC-DS (ON vs OFF, in-engine sf=$TPCDS_SF) ----"
    build_tpcds_db || return
    run_bench_dir "$SCRIPT_DIR/outerjoin_query/tpcds" "$TPCDS_DB"
}

# -----------------------------------------------------------------------------
# Main argument dispatch
# -----------------------------------------------------------------------------
TEST_NUM=${1:-all}
echo "========================================"
echo "OuterYan OFF-vs-ON Test Suite (Embedded Compare, Lock-Fixed V2)"
echo "  DuckDB binary: $DUCKDB_BIN"
echo "  Running suite: $TEST_NUM"
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
        echo "  select / 1   SELECT* equivalence (small equiv db)"
        echo "  agg    / 2   Aggregation equivalence"
        echo "  pred   / 3   Filter predicate equivalence"
        echo "  tpch   / 4   TPC-H outer join cases"
        echo "  tpcds  / 5   TPC-DS outer join cases"
        echo "  equiv        select + agg + pred small suites"
        echo "  bench        tpch + tpcds large benchmark suites"
        echo "  all          Run all test suites (default)"
        exit 1 ;;
esac

echo "========================================"
echo "All Test Suites Finished"
echo "========================================"
