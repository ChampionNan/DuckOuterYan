#!/usr/bin/env bash
# Capture and execute DuckDB/PGPlan/OuterYan for a selected outer-join corpus.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../configs.sh
source "$SCRIPT_DIR/../configs.sh"

CORPUS="${OY_CORPUS:-$SCRIPT_DIR/../outerjoin_query}"
ONLY="all"
PATTERN="*"
LIMIT=0
ROW_CAP="${PGPLAN_SAMPLE_ROWS:-1000}"
RUNS="${PGPLAN_RUNS:-${OY_RUNS:-3}}"
THREADS="${PGPLAN_THREADS:-${OY_THREADS:-1}}"
TIMEOUT_SECS="${PGPLAN_TIMEOUT_SECS:-${OY_TIMEOUT_SECS:-0}}"
DUCKDB_BIN="${DUCKDB_BIN:-}"
PG_DSN="${PG_DSN:-}"
OUT=""

usage() {
    cat <<'USAGE'
Usage:
  corpus_experiment.sh [--only graph|tpch|tpcds|job|bench|all]
      [--pattern GLOB] [--limit N] [--rows N]
      [--corpus DIR] [--duckdb-bin PATH] [--pg-dsn DSN]
      [--runs ODD_N] [--threads N] [--timeout SECONDS] [--out DIR]

For each selected SQL file, capture a fresh PostgreSQL 16.2 typed join tree and
run the complete three-configuration correctness/performance experiment:

  DuckDB, PGPlan, OuterYan

With the default corpus and --only all, this selects all 206 queries: 7 graph,
54 TPC-H, 63 TPC-DS, and 82 JOB.

Graph, TPC-DS, and JOB plans use isolated PostgreSQL schemas populated from at
most --rows rows per DuckDB table (default 1000). TPC-H uses the exact SF0.01
data prepared by setup_pg.sh. Selection order is graph, tpch, tpcds, job and is
locale independent; --limit is global. --pattern is a shell glob on the query
filename without .sql.

Every selected query gets one row in OUT/status.tsv. Failures are recorded and
the remaining queries continue, but any failure makes the final exit status
nonzero. There is no fallback to DuckDB when capture or PGPlan integration
fails.
USAGE
}

die() {
    echo "ERROR: $*" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --only)
            [ $# -ge 2 ] || die "$1 requires a value"
            ONLY="$2"
            shift 2
            ;;
        --pattern)
            [ $# -ge 2 ] || die "$1 requires a value"
            PATTERN="$2"
            shift 2
            ;;
        --limit)
            [ $# -ge 2 ] || die "$1 requires a value"
            LIMIT="$2"
            shift 2
            ;;
        --rows)
            [ $# -ge 2 ] || die "$1 requires a value"
            ROW_CAP="$2"
            shift 2
            ;;
        --corpus)
            [ $# -ge 2 ] || die "$1 requires a value"
            CORPUS="$2"
            shift 2
            ;;
        --duckdb-bin|--bin|-b)
            [ $# -ge 2 ] || die "$1 requires a value"
            DUCKDB_BIN="$2"
            shift 2
            ;;
        --pg-dsn)
            [ $# -ge 2 ] || die "$1 requires a value"
            PG_DSN="$2"
            shift 2
            ;;
        --runs|-n)
            [ $# -ge 2 ] || die "$1 requires a value"
            RUNS="$2"
            shift 2
            ;;
        --threads)
            [ $# -ge 2 ] || die "$1 requires a value"
            THREADS="$2"
            shift 2
            ;;
        --timeout|-t)
            [ $# -ge 2 ] || die "$1 requires a value"
            TIMEOUT_SECS="$2"
            shift 2
            ;;
        --out)
            [ $# -ge 2 ] || die "$1 requires a value"
            OUT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown argument: $1"
            ;;
    esac
done

case "$ONLY" in
    graph) FAMILIES=(graph) ;;
    tpch) FAMILIES=(tpch) ;;
    tpcds) FAMILIES=(tpcds) ;;
    job) FAMILIES=(job) ;;
    bench) FAMILIES=(tpch tpcds job) ;;
    all) FAMILIES=(graph tpch tpcds job) ;;
    *) die "--only must be graph, tpch, tpcds, job, bench, or all" ;;
esac
[[ "$LIMIT" =~ ^[0-9]+$ ]] || die "--limit must be a non-negative integer"
[[ "$ROW_CAP" =~ ^[1-9][0-9]*$ ]] || die "--rows must be a positive integer"
[[ "$RUNS" =~ ^[1-9][0-9]*$ ]] || die "--runs must be a positive integer"
[ $((RUNS % 2)) -eq 1 ] || die "--runs must be odd"
[[ "$THREADS" =~ ^[1-9][0-9]*$ ]] || die "--threads must be a positive integer"
[[ "$TIMEOUT_SECS" =~ ^[0-9]+$ ]] || die "--timeout must be a non-negative integer"
[ -d "$CORPUS" ] || die "corpus directory does not exist: $CORPUS"
CORPUS="$(cd "$CORPUS" && pwd -P)"
[ -x "$DUCKDB_BIN" ] || die "DuckDB binary is not executable: $DUCKDB_BIN"
[ -n "$PG_DSN" ] || die "--pg-dsn is required (or set PG_DSN)"

for helper in setup_pg.sh prepare_sampled_pg.sh make_plan.sh experiment.sh; do
    [ -x "$SCRIPT_DIR/$helper" ] || die "required helper is not executable: $SCRIPT_DIR/$helper"
done

if [ -z "$OUT" ]; then
    OUT="$SCRIPT_DIR/../results/pgplan_corpus_$(date '+%Y%m%d_%H%M%S')"
fi
if [ -e "$OUT" ] && [ -n "$(find "$OUT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    die "--out already exists and is not empty: $OUT"
fi
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd -P)"
mkdir -p "$OUT/artifacts" "$OUT/runs" "$OUT/logs" "$OUT/data_manifests"
STATUS_TSV="$OUT/status.tsv"
printf 'family\tquery\tstatus\tphase\tdetail\tplan\tresult_dir\n' > "$STATUS_TSV"

QUERY_FAMILIES=()
QUERY_PATHS=()
QUERY_LABELS=()
for family in "${FAMILIES[@]}"; do
    query_dir="$CORPUS/$family"
    [ -d "$query_dir" ] || die "selected corpus family is missing: $query_dir"
    while IFS= read -r query_path; do
        label="$(basename "$query_path" .sql)"
        case "$label" in $PATTERN) ;; *) continue ;; esac
        QUERY_FAMILIES+=("$family")
        QUERY_PATHS+=("$query_path")
        QUERY_LABELS+=("$label")
        if [ "$LIMIT" -gt 0 ] && [ "${#QUERY_PATHS[@]}" -ge "$LIMIT" ]; then
            break
        fi
    done < <(find "$query_dir" -maxdepth 1 -type f -name '*.sql' -print | LC_ALL=C sort)
    if [ "$LIMIT" -gt 0 ] && [ "${#QUERY_PATHS[@]}" -ge "$LIMIT" ]; then
        break
    fi
done
[ "${#QUERY_PATHS[@]}" -gt 0 ] || \
    die "no corpus queries matched (only=$ONLY pattern=$PATTERN)"

db_for_family() {
    case "$1" in
        graph) printf '%s' "${GRAPH_DB:-}" ;;
        tpch) printf '%s' "${TPCH_DB:-}" ;;
        tpcds) printf '%s' "${TPCDS_DB:-}" ;;
        job) printf '%s' "${JOB_DB:-}" ;;
        *) return 1 ;;
    esac
}

for family in "${FAMILIES[@]}"; do
    needed=0
    for selected_family in "${QUERY_FAMILIES[@]}"; do
        [ "$selected_family" != "$family" ] || needed=1
    done
    [ "$needed" -eq 1 ] || continue
    family_db="$(db_for_family "$family")" || die "unknown family: $family"
    [ -f "$family_db" ] || die "$family DuckDB database does not exist: $family_db"
done

sanitize_detail() {
    local log="$1" detail
    detail="$(tail -n 1 "$log" 2>/dev/null || true)"
    detail="${detail//$'\t'/ }"
    detail="${detail//$'\r'/ }"
    detail="${detail//$'\n'/ }"
    printf '%s' "${detail:-no diagnostic emitted}"
}

append_status() {
    local family="$1" query="$2" status="$3" phase="$4" detail="$5" plan="$6" result_dir="$7"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$family" "$query" "$status" "$phase" "$detail" "$plan" "$result_dir" \
        >> "$STATUS_TSV"
}

echo "[pgplan] selected ${#QUERY_PATHS[@]} query(s); status=$STATUS_TSV"
SETUP_LOG="$OUT/logs/setup_pg.log"
if ! bash "$SCRIPT_DIR/setup_pg.sh" > "$SETUP_LOG" 2>&1; then
    detail="$(sanitize_detail "$SETUP_LOG")"
    for index in "${!QUERY_PATHS[@]}"; do
        relative="${QUERY_PATHS[$index]#$CORPUS/}"
        append_status "${QUERY_FAMILIES[$index]}" "$relative" FAIL setup "$detail" "" ""
    done
    echo "ERROR: PostgreSQL setup failed: $detail" >&2
    echo "[pgplan] status=$STATUS_TSV" >&2
    exit 1
fi

PREPARED_GRAPH=0
PREPARED_TPCH=0
PREPARED_TPCDS=0
PREPARED_JOB=0
CURRENT_SCHEMA=""
CURRENT_PLAN_DATA=""

prepare_family() {
    local family="$1" family_db prepare_log force_args=()
    case "$family" in
        graph)
            [ "$PREPARED_GRAPH" -eq 0 ] || return 0
            CURRENT_SCHEMA="pgplan_graph"
            CURRENT_PLAN_DATA="graph-duckdb-sample-$ROW_CAP"
            ;;
        tpch)
            [ "$PREPARED_TPCH" -eq 0 ] || return 0
            CURRENT_SCHEMA="public"
            CURRENT_PLAN_DATA="tpch-sf0.01"
            PREPARED_TPCH=1
            return 0
            ;;
        tpcds)
            [ "$PREPARED_TPCDS" -eq 0 ] || return 0
            CURRENT_SCHEMA="pgplan_tpcds"
            CURRENT_PLAN_DATA="tpcds-duckdb-sample-$ROW_CAP"
            ;;
        job)
            [ "$PREPARED_JOB" -eq 0 ] || return 0
            CURRENT_SCHEMA="pgplan_job"
            CURRENT_PLAN_DATA="job-duckdb-sample-$ROW_CAP"
            ;;
        *) return 2 ;;
    esac

    family_db="$(db_for_family "$family")" || return 2
    prepare_log="$OUT/logs/prepare_$family.log"
    if [ "${PGPLAN_SETUP:-${PG_REPLAY_SETUP:-source}}" != "external" ] || \
            [ "${PGPLAN_FORCE_SAMPLED_DATA:-${PGPLAN_FORCE_DATA:-${PG_REPLAY_FORCE_DATA:-0}}}" = "1" ]; then
        force_args=(--force)
    fi
    if ! bash "$SCRIPT_DIR/prepare_sampled_pg.sh" \
            --family "$family" \
            --duckdb-db "$family_db" \
            --pg-dsn "$PG_DSN" \
            --rows "$ROW_CAP" \
            --manifest "$OUT/data_manifests/$family.tsv" \
            "${force_args[@]}" > "$prepare_log" 2>&1; then
        PREPARE_FAILURE_DETAIL="$(sanitize_detail "$prepare_log")"
        return 1
    fi
    case "$family" in
        graph) PREPARED_GRAPH=1 ;;
        tpcds) PREPARED_TPCDS=1 ;;
        job) PREPARED_JOB=1 ;;
    esac
    return 0
}

FAILED=0
SKIP_GRAPH=0
SKIP_TPCH=0
SKIP_TPCDS=0
SKIP_JOB=0
for index in "${!QUERY_PATHS[@]}"; do
    family="${QUERY_FAMILIES[$index]}"
    query="${QUERY_PATHS[$index]}"
    label="${QUERY_LABELS[$index]}"
    relative="${query#$CORPUS/}"
    case "$family" in
        graph) family_skipped="$SKIP_GRAPH" ;;
        tpch) family_skipped="$SKIP_TPCH" ;;
        tpcds) family_skipped="$SKIP_TPCDS" ;;
        job) family_skipped="$SKIP_JOB" ;;
    esac
    if [ "$family_skipped" -eq 1 ]; then
        append_status "$family" "$relative" FAIL prepare "$PREPARE_FAILURE_DETAIL" "" ""
        FAILED=1
        continue
    fi

    if ! prepare_family "$family"; then
        case "$family" in
            graph) SKIP_GRAPH=1 ;;
            tpch) SKIP_TPCH=1 ;;
            tpcds) SKIP_TPCDS=1 ;;
            job) SKIP_JOB=1 ;;
        esac
        append_status "$family" "$relative" FAIL prepare "$PREPARE_FAILURE_DETAIL" "" ""
        echo "[pgplan] FAIL $relative (prepare: $PREPARE_FAILURE_DETAIL)" >&2
        FAILED=1
        continue
    fi

    # prepare_family returns early once a family is ready, so restore these
    # deterministic values for every query in that family.
    case "$family" in
        graph)
            CURRENT_SCHEMA="pgplan_graph"
            CURRENT_PLAN_DATA="graph-duckdb-sample-$ROW_CAP"
            ;;
        tpch)
            CURRENT_SCHEMA="public"
            CURRENT_PLAN_DATA="tpch-sf0.01"
            ;;
        tpcds)
            CURRENT_SCHEMA="pgplan_tpcds"
            CURRENT_PLAN_DATA="tpcds-duckdb-sample-$ROW_CAP"
            ;;
        job)
            CURRENT_SCHEMA="pgplan_job"
            CURRENT_PLAN_DATA="job-duckdb-sample-$ROW_CAP"
            ;;
    esac

    plan_dir="$OUT/artifacts/$family"
    result_dir="$OUT/runs/$family/$label"
    mkdir -p "$plan_dir" "$(dirname "$result_dir")"
    plan="$plan_dir/$label.pg.json"
    capture_log="$OUT/logs/${family}__${label}__capture.log"
    experiment_log="$OUT/logs/${family}__${label}__experiment.log"

    echo "[pgplan] capture $relative"
    if ! bash "$SCRIPT_DIR/make_plan.sh" \
            --pg-dsn "$PG_DSN" \
            --pg-schema "$CURRENT_SCHEMA" \
            --plan-data "$CURRENT_PLAN_DATA" \
            --query "$query" \
            --out "$plan" \
            --expected-pg-version "${PGPLAN_VERSION_NUM:-160002}" \
            > "$capture_log" 2>&1; then
        detail="$(sanitize_detail "$capture_log")"
        append_status "$family" "$relative" FAIL capture "$detail" "$plan" ""
        echo "[pgplan] FAIL $relative (capture: $detail)" >&2
        FAILED=1
        continue
    fi

    execution_db="$(db_for_family "$family")"
    echo "[pgplan] execute $relative"
    if ! PGPLAN_TIMEOUT_SECS="$TIMEOUT_SECS" \
            PGPLAN_TIMEOUT_GRACE="${PGPLAN_TIMEOUT_GRACE:-${OY_BATCH_GRACE_SECS:-30}}" \
            PGPLAN_TMPDIR="${PGPLAN_TMPDIR:-${OY_TMPDIR:-$OUT/tmp}}" \
            PGPLAN_KEEP_CORRECTNESS_FILES="${PGPLAN_KEEP_CORRECTNESS_FILES:-0}" \
            bash "$SCRIPT_DIR/experiment.sh" \
                --duckdb-bin "$DUCKDB_BIN" \
                --execution-db "$execution_db" \
                --query "$query" \
                --plan "$plan" \
                --runs "$RUNS" \
                --threads "$THREADS" \
                --out "$result_dir" \
                > "$experiment_log" 2>&1; then
        detail="$(sanitize_detail "$experiment_log")"
        append_status "$family" "$relative" FAIL execute "$detail" "$plan" "$result_dir"
        echo "[pgplan] FAIL $relative (execute: $detail)" >&2
        FAILED=1
        continue
    fi

    append_status "$family" "$relative" PASS complete complete "$plan" "$result_dir"
    echo "[pgplan] PASS $relative"
done

PASS_COUNT="$(awk -F '\t' 'NR > 1 && $3 == "PASS" {count++} END {print count + 0}' "$STATUS_TSV")"
FAIL_COUNT="$(awk -F '\t' 'NR > 1 && $3 == "FAIL" {count++} END {print count + 0}' "$STATUS_TSV")"
echo "[pgplan] complete: pass=$PASS_COUNT fail=$FAIL_COUNT status=$STATUS_TSV"
[ "$FAILED" -eq 0 ]
