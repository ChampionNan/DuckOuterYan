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
CORRECTNESS_MODE="${PGPLAN_CORRECTNESS_MODE:-${PG_REPLAY_CORRECTNESS_MODE:-target}}"
RUNS="${PGPLAN_RUNS:-${OY_RUNS:-3}}"
THREADS="${PGPLAN_THREADS:-${OY_THREADS:-1}}"
TIMEOUT_SECS="${PGPLAN_TIMEOUT_SECS:-${OY_TIMEOUT_SECS:-0}}"
CAPTURE_TIMEOUT_SECS="${PGPLAN_CAPTURE_TIMEOUT_SECS:-${PG_REPLAY_CAPTURE_TIMEOUT_SECS:-300}}"
CORRECTNESS_GRAPH_ROWS="${PGPLAN_CORRECTNESS_GRAPH_ROWS:-500}"
CORRECTNESS_JOB_ROWS="${PGPLAN_CORRECTNESS_JOB_ROWS:-1000}"
CORRECTNESS_MAX_RESULT_ROWS="${PGPLAN_CORRECTNESS_MAX_RESULT_ROWS:-2000000}"
CORRECTNESS_QUERY_TIMEOUT_SECS="${PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS:-30}"
DUCKDB_BIN="${DUCKDB_BIN:-}"
PG_DSN="${PG_DSN:-}"
OUT=""

usage() {
    cat <<'USAGE'
Usage:
  corpus_experiment.sh [--only graph|tpch|tpcds|job|bench|all]
      [--pattern GLOB] [--limit N] [--rows N]
      [--correctness-mode target|bounded]
      [--corpus DIR] [--duckdb-bin PATH] [--pg-dsn DSN]
      [--runs ODD_N] [--threads N] [--timeout SECONDS]
      [--capture-timeout SECONDS] [--out DIR]

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

Exact result comparison uses the configured target DuckDB database by default,
so every emitted row is included in the three bare-query multiset checks.
`--correctness-mode bounded` explicitly selects a quicker diagnostic mode that
builds one deterministic small DuckDB correctness database per selected family.
EXPLAIN, PGPlan semantic verification, and timing always use the target database.
--runs controls the positive odd number of measured TM executions after one
warm-up. Every T1 configuration uses exactly one warm-up and one measured run.

Every selected query gets one row in OUT/status.tsv. PostgreSQL plain-EXPLAIN
or DuckDB execution timeouts are recorded as SKIP, their remaining experiment
is not run, and the next query continues. Both SKIP and FAIL make the corpus
exit nonzero because a successful corpus must completely test every selected
query. There is no fallback to DuckDB when capture or PGPlan integration fails.
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
        --correctness-mode)
            [ $# -ge 2 ] || die "$1 requires a value"
            CORRECTNESS_MODE="$2"
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
        --capture-timeout)
            [ $# -ge 2 ] || die "$1 requires a value"
            CAPTURE_TIMEOUT_SECS="$2"
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
case "$CORRECTNESS_MODE" in
    target|bounded) ;;
    *) die "--correctness-mode must be target or bounded" ;;
esac
[[ "$RUNS" =~ ^[1-9][0-9]*$ ]] || die "--runs must be a positive integer"
[ $((RUNS % 2)) -eq 1 ] || die "--runs must be odd"
[[ "$THREADS" =~ ^[1-9][0-9]*$ ]] || die "--threads must be a positive integer"
[[ "$TIMEOUT_SECS" =~ ^[0-9]+$ ]] || die "--timeout must be a non-negative integer"
[[ "$CAPTURE_TIMEOUT_SECS" =~ ^[0-9]+$ ]] || \
    die "--capture-timeout must be a non-negative integer"
if [ "$CORRECTNESS_MODE" = "bounded" ]; then
    [[ "$CORRECTNESS_GRAPH_ROWS" =~ ^[1-9][0-9]*$ ]] || \
        die "PGPLAN_CORRECTNESS_GRAPH_ROWS must be a positive integer"
    [[ "$CORRECTNESS_JOB_ROWS" =~ ^[1-9][0-9]*$ ]] || \
        die "PGPLAN_CORRECTNESS_JOB_ROWS must be a positive integer"
    [[ "$CORRECTNESS_MAX_RESULT_ROWS" =~ ^[1-9][0-9]*$ ]] || \
        die "PGPLAN_CORRECTNESS_MAX_RESULT_ROWS must be a positive integer"
    [[ "$CORRECTNESS_QUERY_TIMEOUT_SECS" =~ ^[1-9][0-9]*$ ]] || \
        die "PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS must be a positive integer"
fi
[ -d "$CORPUS" ] || die "corpus directory does not exist: $CORPUS"
CORPUS="$(cd "$CORPUS" && pwd -P)"
[ -x "$DUCKDB_BIN" ] || die "DuckDB binary is not executable: $DUCKDB_BIN"
[ -n "$PG_DSN" ] || die "--pg-dsn is required (or set PG_DSN)"

for helper in setup_pg.sh prepare_sampled_pg.sh make_plan.sh experiment.sh \
        summarize_corpus.sh; do
    [ -x "$SCRIPT_DIR/$helper" ] || die "required helper is not executable: $SCRIPT_DIR/$helper"
done
if [ "$CORRECTNESS_MODE" = "bounded" ]; then
    [ -x "$SCRIPT_DIR/prepare_correctness_db.sh" ] || \
        die "required helper is not executable: $SCRIPT_DIR/prepare_correctness_db.sh"
fi

if [ -z "$OUT" ]; then
    OUT="$SCRIPT_DIR/../results/pgplan_corpus_$(date '+%Y%m%d_%H%M%S')"
fi
if [ -e "$OUT" ] && [ -n "$(find "$OUT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    die "--out already exists and is not empty: $OUT"
fi
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd -P)"
mkdir -p "$OUT/artifacts" "$OUT/runs" "$OUT/logs" "$OUT/data_manifests" \
    "$OUT/correctness_dbs" "$OUT/query_snapshots"
STATUS_TSV="$OUT/status.tsv"
printf 'family\tquery\tstatus\tphase\tdetail\tplan\tresult_dir\n' > "$STATUS_TSV"

QUERY_FAMILIES=()
QUERY_PATHS=()
QUERY_LABELS=()
QUERY_RELATIVES=()
for family in "${FAMILIES[@]}"; do
    query_dir="$CORPUS/$family"
    [ -d "$query_dir" ] || die "selected corpus family is missing: $query_dir"
    while IFS= read -r query_path; do
        label="$(basename "$query_path" .sql)"
        case "$label" in $PATTERN) ;; *) continue ;; esac
        QUERY_FAMILIES+=("$family")
        QUERY_PATHS+=("$query_path")
        QUERY_LABELS+=("$label")
        QUERY_RELATIVES+=("${query_path#$CORPUS/}")
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

# Freeze the selected SQL before PostgreSQL setup or data preparation. Capture,
# correctness-fixture construction, and all three DuckDB modes consume these
# same immutable bytes even if the generated corpus is edited concurrently.
for index in "${!QUERY_PATHS[@]}"; do
    snapshot="$OUT/query_snapshots/${QUERY_RELATIVES[$index]}"
    mkdir -p "$(dirname "$snapshot")"
    cp -- "${QUERY_PATHS[$index]}" "$snapshot"
    QUERY_PATHS[$index]="$snapshot"
done

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

# Append the query's terminal status before asking the report formatter to
# render that exact row. A formatter problem must not add a second status row
# or stop the remaining corpus queries, but it does make the corpus fail.
record_query_status() {
    local row_number="$1"
    shift
    local formatter_rc

    append_status "$@"
    if bash "$SCRIPT_DIR/summarize_corpus.sh" \
            --result-dir "$OUT" \
            --print-row "$row_number" \
            --total "${#QUERY_PATHS[@]}"; then
        return 0
    else
        formatter_rc=$?
    fi
    FAILED=1
    echo "ERROR: could not format three-way result row $row_number (exit=$formatter_rc)" >&2
    return 0
}

sha256_file() {
    local path="$1" digest
    if command -v sha256sum >/dev/null 2>&1; then
        digest="$(sha256sum -- "$path" | awk '{print $1}')"
    elif command -v shasum >/dev/null 2>&1; then
        digest="$(shasum -a 256 -- "$path" | awk '{print $1}')"
    elif command -v openssl >/dev/null 2>&1; then
        digest="$(openssl dgst -sha256 "$path" | awk '{print $NF}')"
    else
        echo "sha256sum, shasum, or openssl is required for correctness provenance" >&2
        return 1
    fi
    [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || {
        echo "invalid SHA-256 digest for $path: $digest" >&2
        return 1
    }
    printf '%s' "$digest"
}

attach_correctness_provenance() {
    local family="$1" result_dir="$2"
    local source_manifest="$OUT/data_manifests/${family}_correctness.tsv"
    local source_fingerprints="$OUT/data_manifests/${family}_correctness.sha256.tsv"
    local provenance="$result_dir/provenance"
    local run_manifest="$provenance/manifest.txt"
    local database_sha manifest_sha
    if [ ! -r "$source_manifest" ] || [ ! -r "$source_fingerprints" ]; then
        echo "correctness manifest or fingerprint file is missing for $family" >&2
        return 1
    fi
    database_sha="$(awk -F '\t' '$1 == "database" {print $2}' "$source_fingerprints")"
    manifest_sha="$(awk -F '\t' '$1 == "manifest" {print $2}' "$source_fingerprints")"
    if ! [[ "$database_sha" =~ ^[0-9a-f]{64}$ ]] || \
            ! [[ "$manifest_sha" =~ ^[0-9a-f]{64}$ ]]; then
        echo "invalid correctness provenance digest for $family" >&2
        return 1
    fi
    if ! mkdir -p "$provenance" || \
            ! cp -- "$source_manifest" "$provenance/correctness_db_manifest.tsv" || \
            ! cp -- "$source_fingerprints" "$provenance/correctness_db_fingerprints.tsv"; then
        echo "could not copy correctness provenance for $family" >&2
        return 1
    fi
    if [ -f "$run_manifest" ]; then
        if ! {
            printf 'correctness_db_sha256=%s\n' "$database_sha"
            printf 'correctness_db_manifest=%s\n' "$provenance/correctness_db_manifest.tsv"
            printf 'correctness_db_manifest_sha256=%s\n' "$manifest_sha"
        } >> "$run_manifest"; then
            echo "could not append correctness provenance for $family" >&2
            return 1
        fi
    fi
    return 0
}

FAILED=0
QUERY_SEPARATOR="--------------------------------------------------------------------------------"

finalize_corpus() {
    local pass_count fail_count skip_count summary_rc
    local summary_log="$OUT/logs/summarize_corpus.log"

    printf '\n%s\n' "$QUERY_SEPARATOR"
    pass_count="$(awk -F '\t' 'NR > 1 && $3 == "PASS" {count++} END {print count + 0}' "$STATUS_TSV")"
    fail_count="$(awk -F '\t' 'NR > 1 && $3 == "FAIL" {count++} END {print count + 0}' "$STATUS_TSV")"
    skip_count="$(awk -F '\t' 'NR > 1 && $3 == "SKIP" {count++} END {print count + 0}' "$STATUS_TSV")"

    if bash "$SCRIPT_DIR/summarize_corpus.sh" --result-dir "$OUT" \
            2>&1 | tee "$summary_log"; then
        summary_rc=0
    else
        summary_rc=$?
        FAILED=1
        echo "ERROR: three-way corpus report generation failed (exit=$summary_rc; log=$summary_log)" >&2
    fi

    echo "[three-way] complete: selected=${#QUERY_PATHS[@]} compared=$pass_count skip=$skip_count fail=$fail_count status=$STATUS_TSV"
    echo "[three-way] reports: comparison_tsv=$OUT/comparison.tsv comparison_csv=$OUT/comparison.csv comparison_log=$OUT/comparison.log summary_tsv=$OUT/summary.tsv failures_tsv=$OUT/failures.tsv"
    [ "$FAILED" -eq 0 ]
}

echo "[three-way] selected ${#QUERY_PATHS[@]} query(s); status=$STATUS_TSV"
SETUP_LOG="$OUT/logs/setup_pg.log"
if ! bash "$SCRIPT_DIR/setup_pg.sh" > "$SETUP_LOG" 2>&1; then
    detail="$(sanitize_detail "$SETUP_LOG")"
    for index in "${!QUERY_PATHS[@]}"; do
        relative="${QUERY_RELATIVES[$index]}"
        append_status "${QUERY_FAMILIES[$index]}" "$relative" FAIL setup "$detail" "" ""
    done
    echo "ERROR: PostgreSQL setup failed: $detail" >&2
    FAILED=1
    finalize_rc=0
    finalize_corpus || finalize_rc=$?
    exit "$finalize_rc"
fi

PREPARED_GRAPH=0
PREPARED_TPCH=0
PREPARED_TPCDS=0
PREPARED_JOB=0
CURRENT_SCHEMA=""
CURRENT_PLAN_DATA=""
CURRENT_CORRECTNESS_DB=""

prepare_family() {
    local family="$1" family_db correctness_db correctness_log prepare_log correctness_rows
    local correctness_manifest correctness_fingerprints correctness_db_sha correctness_manifest_sha
    local force_args=() correctness_args=()
    case "$family" in
        graph)
            [ "$PREPARED_GRAPH" -eq 0 ] || return 0
            CURRENT_SCHEMA="pgplan_graph"
            CURRENT_PLAN_DATA="graph-duckdb-sample-$ROW_CAP"
            correctness_rows="$CORRECTNESS_GRAPH_ROWS"
            ;;
        tpch)
            [ "$PREPARED_TPCH" -eq 0 ] || return 0
            CURRENT_SCHEMA="public"
            CURRENT_PLAN_DATA="tpch-sf0.01"
            correctness_rows=""
            ;;
        tpcds)
            [ "$PREPARED_TPCDS" -eq 0 ] || return 0
            CURRENT_SCHEMA="pgplan_tpcds"
            CURRENT_PLAN_DATA="tpcds-duckdb-sample-$ROW_CAP"
            correctness_rows=""
            ;;
        job)
            [ "$PREPARED_JOB" -eq 0 ] || return 0
            CURRENT_SCHEMA="pgplan_job"
            CURRENT_PLAN_DATA="job-duckdb-sample-$ROW_CAP"
            correctness_rows="$CORRECTNESS_JOB_ROWS"
            ;;
        *) return 2 ;;
    esac

    family_db="$(db_for_family "$family")" || return 2
    if [ "$CORRECTNESS_MODE" = "bounded" ]; then
        correctness_db="$OUT/correctness_dbs/$family.duckdb"
        correctness_log="$OUT/logs/prepare_correctness_$family.log"
        CURRENT_CORRECTNESS_DB="$correctness_db"
        correctness_args=(
            --family "$family"
            --source-db "$family_db"
            --out "$correctness_db"
            --query-dir "$OUT/query_snapshots/$family"
            --max-result-rows "$CORRECTNESS_MAX_RESULT_ROWS"
            --query-timeout "$CORRECTNESS_QUERY_TIMEOUT_SECS"
            --duckdb-bin "$DUCKDB_BIN"
            --manifest "$OUT/data_manifests/${family}_correctness.tsv"
        )
        if [ -n "$correctness_rows" ]; then
            correctness_args+=(--rows "$correctness_rows")
        fi
        echo "[pgplan] prepare bounded $family correctness DB: $correctness_db"
        if ! bash "$SCRIPT_DIR/prepare_correctness_db.sh" \
                "${correctness_args[@]}" > "$correctness_log" 2>&1; then
            PREPARE_FAILURE_DETAIL="$(sanitize_detail "$correctness_log")"
            return 1
        fi
        correctness_manifest="$OUT/data_manifests/${family}_correctness.tsv"
        correctness_fingerprints="$OUT/data_manifests/${family}_correctness.sha256.tsv"
        if ! correctness_db_sha="$(sha256_file "$correctness_db")" || \
                ! correctness_manifest_sha="$(sha256_file "$correctness_manifest")"; then
            PREPARE_FAILURE_DETAIL="could not fingerprint the $family correctness database"
            return 1
        fi
        if ! {
            printf 'object\tsha256\tpath\n'
            printf 'database\t%s\t%s\n' "$correctness_db_sha" "$correctness_db"
            printf 'manifest\t%s\t%s\n' "$correctness_manifest_sha" "$correctness_manifest"
        } > "$correctness_fingerprints"; then
            PREPARE_FAILURE_DETAIL="could not write the $family correctness fingerprints"
            return 1
        fi
    else
        CURRENT_CORRECTNESS_DB="$family_db"
    fi

    # setup_pg.sh already prepared the exact SF0.01 PostgreSQL data. Other
    # families additionally need their isolated PostgreSQL plan-selection
    # schema populated from the target DuckDB database.
    if [ "$family" = "tpch" ]; then
        PREPARED_TPCH=1
        return 0
    fi

    prepare_log="$OUT/logs/prepare_pg_$family.log"
    echo "[pgplan] prepare minimal PostgreSQL $family plan-selection data"
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

SKIP_GRAPH=0
SKIP_TPCH=0
SKIP_TPCDS=0
SKIP_JOB=0
for index in "${!QUERY_PATHS[@]}"; do
    family="${QUERY_FAMILIES[$index]}"
    query="${QUERY_PATHS[$index]}"
    label="${QUERY_LABELS[$index]}"
    relative="${QUERY_RELATIVES[$index]}"
    printf '\n%s\n' "$QUERY_SEPARATOR"
    printf '[three-way] query %d/%d: %s\n' \
        "$((index + 1))" "${#QUERY_PATHS[@]}" "$relative"
    printf '%s\n' "$QUERY_SEPARATOR"
    case "$family" in
        graph) family_skipped="$SKIP_GRAPH" ;;
        tpch) family_skipped="$SKIP_TPCH" ;;
        tpcds) family_skipped="$SKIP_TPCDS" ;;
        job) family_skipped="$SKIP_JOB" ;;
    esac
    if [ "$family_skipped" -eq 1 ]; then
        record_query_status "$((index + 1))" \
            "$family" "$relative" FAIL prepare "$PREPARE_FAILURE_DETAIL" "" ""
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
        record_query_status "$((index + 1))" \
            "$family" "$relative" FAIL prepare "$PREPARE_FAILURE_DETAIL" "" ""
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
            if [ "$CORRECTNESS_MODE" = "bounded" ]; then
                CURRENT_CORRECTNESS_DB="$OUT/correctness_dbs/graph.duckdb"
            else
                CURRENT_CORRECTNESS_DB="$(db_for_family graph)"
            fi
            ;;
        tpch)
            CURRENT_SCHEMA="public"
            CURRENT_PLAN_DATA="tpch-sf0.01"
            if [ "$CORRECTNESS_MODE" = "bounded" ]; then
                CURRENT_CORRECTNESS_DB="$OUT/correctness_dbs/tpch.duckdb"
            else
                CURRENT_CORRECTNESS_DB="$(db_for_family tpch)"
            fi
            ;;
        tpcds)
            CURRENT_SCHEMA="pgplan_tpcds"
            CURRENT_PLAN_DATA="tpcds-duckdb-sample-$ROW_CAP"
            if [ "$CORRECTNESS_MODE" = "bounded" ]; then
                CURRENT_CORRECTNESS_DB="$OUT/correctness_dbs/tpcds.duckdb"
            else
                CURRENT_CORRECTNESS_DB="$(db_for_family tpcds)"
            fi
            ;;
        job)
            CURRENT_SCHEMA="pgplan_job"
            CURRENT_PLAN_DATA="job-duckdb-sample-$ROW_CAP"
            if [ "$CORRECTNESS_MODE" = "bounded" ]; then
                CURRENT_CORRECTNESS_DB="$OUT/correctness_dbs/job.duckdb"
            else
                CURRENT_CORRECTNESS_DB="$(db_for_family job)"
            fi
            ;;
    esac

    plan_dir="$OUT/artifacts/$family"
    result_dir="$OUT/runs/$family/$label"
    mkdir -p "$plan_dir" "$(dirname "$result_dir")"
    plan="$plan_dir/$label.pg.json"
    capture_log="$OUT/logs/${family}__${label}__capture.log"
    experiment_log="$OUT/logs/${family}__${label}__experiment.log"

    echo "[pgplan] capture $relative (plain EXPLAIN timeout=${CAPTURE_TIMEOUT_SECS}s)"
    if bash "$SCRIPT_DIR/make_plan.sh" \
            --pg-dsn "$PG_DSN" \
            --pg-schema "$CURRENT_SCHEMA" \
            --plan-data "$CURRENT_PLAN_DATA" \
            --query "$query" \
            --out "$plan" \
            --expected-pg-version "${PGPLAN_VERSION_NUM:-160002}" \
            --capture-timeout "$CAPTURE_TIMEOUT_SECS" \
            > "$capture_log" 2>&1; then
        capture_rc=0
    else
        capture_rc=$?
    fi
    if [ "$capture_rc" -eq 124 ]; then
        detail="$(sanitize_detail "$capture_log")"
        record_query_status "$((index + 1))" \
            "$family" "$relative" SKIP capture_timeout "$detail" "" ""
        echo "[pgplan] SKIP $relative (capture timeout: $detail)"
        FAILED=1
        continue
    fi
    if [ "$capture_rc" -ne 0 ]; then
        detail="$(sanitize_detail "$capture_log")"
        record_query_status "$((index + 1))" \
            "$family" "$relative" FAIL capture "$detail" "$plan" ""
        echo "[pgplan] FAIL $relative (capture: $detail)" >&2
        FAILED=1
        continue
    fi

    execution_db="$(db_for_family "$family")"
    echo "[three-way] execute $relative (correctness=$CORRECTNESS_MODE-$family; target EXPLAIN/timing; per-step timeout=${TIMEOUT_SECS}s; log=$experiment_log)"
    if PGPLAN_TIMEOUT_SECS="$TIMEOUT_SECS" \
            PGPLAN_TIMEOUT_GRACE="${PGPLAN_TIMEOUT_GRACE:-${OY_BATCH_GRACE_SECS:-30}}" \
            PGPLAN_TMPDIR="${PGPLAN_TMPDIR:-${OY_TMPDIR:-$OUT/tmp}}" \
            PGPLAN_KEEP_CORRECTNESS_FILES="${PGPLAN_KEEP_CORRECTNESS_FILES:-0}" \
            bash "$SCRIPT_DIR/experiment.sh" \
                --duckdb-bin "$DUCKDB_BIN" \
                --execution-db "$execution_db" \
                --correctness-db "$CURRENT_CORRECTNESS_DB" \
                --query "$query" \
                --plan "$plan" \
                --runs "$RUNS" \
                --threads "$THREADS" \
                --out "$result_dir" \
                2>&1 | tee "$experiment_log"; then
        experiment_rc=0
    else
        experiment_rc=$?
    fi
    if [ "$CORRECTNESS_MODE" = "bounded" ]; then
        provenance_log="$OUT/logs/${family}__${label}__correctness_provenance.log"
        if ! attach_correctness_provenance "$family" "$result_dir" \
                > "$provenance_log" 2>&1; then
            detail="$(sanitize_detail "$provenance_log")"
            record_query_status "$((index + 1))" \
                "$family" "$relative" FAIL provenance "$detail" "$plan" "$result_dir"
            echo "[three-way] FAIL $relative (provenance: $detail)" >&2
            FAILED=1
            continue
        fi
    fi
    if [ "$experiment_rc" -eq 124 ]; then
        detail="$(sanitize_detail "$experiment_log")"
        record_query_status "$((index + 1))" \
            "$family" "$relative" SKIP execute_timeout "$detail" "$plan" "$result_dir"
        echo "[three-way] SKIP $relative (execution timeout: $detail)"
        FAILED=1
        continue
    fi
    if [ "$experiment_rc" -ne 0 ]; then
        detail="$(sanitize_detail "$experiment_log")"
        record_query_status "$((index + 1))" \
            "$family" "$relative" FAIL execute "$detail" "$plan" "$result_dir"
        echo "[three-way] FAIL $relative (execute: $detail)" >&2
        FAILED=1
        continue
    fi

    record_query_status "$((index + 1))" \
        "$family" "$relative" PASS complete complete "$plan" "$result_dir"
    echo "[three-way] PASS $relative"
done

finalize_rc=0
finalize_corpus || finalize_rc=$?
exit "$finalize_rc"
