#!/usr/bin/env bash
# Capture and execute DuckDB/PGPlan/OuterYan for a selected outer-join corpus.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../configs.sh
source "$SCRIPT_DIR/../configs.sh"

CORPUS="${OY_CORPUS:-$SCRIPT_DIR/../outerjoin_benchmark/benchmark}"
ONLY="all"
PATTERN="*"
LIMIT=0
ROW_CAP="${PGPLAN_SAMPLE_ROWS:-1000}"
PLAN_CACHE="${PGPLAN_PLAN_CACHE:-$OY_REPO_ROOT/auto_test/pgplan/plans}"
COMPARISON_MODE="${PGPLAN_COMPARISON_MODE:-both}"
CORRECTNESS_MODE="${PGPLAN_CORRECTNESS_MODE:-${PG_REPLAY_CORRECTNESS_MODE:-target}}"
CORRECTNESS_FROM="${PGPLAN_CORRECTNESS_FROM:-${PG_REPLAY_CORRECTNESS_FROM:-}}"
REUSE_FROM="${PGPLAN_REUSE_FROM:-}"
RUNS="${PGPLAN_RUNS:-${OY_RUNS:-3}}"
THREADS="${PGPLAN_THREADS:-${OY_THREADS:-1}}"
TIMEOUT_SECS="${PGPLAN_TIMEOUT_SECS:-${OY_TIMEOUT_SECS:-0}}"
CAPTURE_TIMEOUT_SECS="${PGPLAN_CAPTURE_TIMEOUT_SECS:-${PG_REPLAY_CAPTURE_TIMEOUT_SECS:-300}}"
CORRECTNESS_GRAPH_ROWS="${PGPLAN_CORRECTNESS_GRAPH_ROWS:-500}"
CORRECTNESS_JOB_ROWS="${PGPLAN_CORRECTNESS_JOB_ROWS:-1000}"
CORRECTNESS_MAX_RESULT_ROWS="${PGPLAN_CORRECTNESS_MAX_RESULT_ROWS:-2000000}"
CORRECTNESS_QUERY_TIMEOUT_SECS="${PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS:-30}"
DUCKDB_BIN="${DUCKDB_BIN:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PG_DSN="${PG_DSN:-}"
OUT=""

usage() {
    cat <<'USAGE'
Usage:
  corpus_experiment.sh [--only graph|tpch|tpcds|job|bench|all]
      [--pattern GLOB] [--limit N] [--rows N]
      [--correctness-mode target|bounded|reuse]
      [--correctness-from PRIOR_CORPUS_DIR]
      [--reuse-from PRIOR_CORPUS_DIR]
      [--plan-cache DIR]
      [--comparison-mode both|pgplan-only|none]
      [--skip1 | --skip2 | --performance-only]
      [--corpus DIR] [--duckdb-bin PATH] [--pg-dsn DSN]
      [--runs ODD_N] [--threads N] [--timeout SECONDS]
      [--capture-timeout SECONDS] [--out DIR]

For each selected SQL file, validate and copy a persistent cached PostgreSQL
16.2 typed join tree or capture it when absent/stale, then run the selected
correctness/performance comparisons:

  DuckDB, PGPlan, OuterYan

With the default corpus and --only all, this selects all 224 queries: 25 graph,
54 TPC-H, 63 TPC-DS, and 82 JOB.

Fresh graph, TPC-DS, and JOB plans use isolated PostgreSQL schemas populated from at
most --rows rows per DuckDB table (default 1000). TPC-H uses the exact SF0.01
data prepared by setup_pg.sh. Selection order is graph, tpch, tpcds, job and is
locale independent; --limit is global. --pattern is a shell glob on the query
filename without .sql.

Exact result comparison uses the configured target DuckDB database by default,
so every emitted row is included in the three bare-query multiset checks.
`--correctness-mode bounded` explicitly selects a quicker diagnostic mode that
builds one deterministic small DuckDB correctness database per selected family.
`--correctness-mode reuse` is a performance-only mode. It requires
`--correctness-from` naming a completed prior corpus and validates the sealed
target-scale correctness receipt at runs/FAMILY/QUERY_LABEL for every query.
Missing, stale, mismatched, or unsafe receipts fail that query; reuse never
falls back to a new result comparison.
`--reuse-from` is the normal performance-rerun shortcut: it selects correctness
reuse and also copies each query's prior PGPlan artifact into the new run. It
skips PostgreSQL setup, sampled-data preparation, and plan capture. The copied
artifact is still query-hash/import validated, and the new run is self-contained.
EXPLAIN, PGPlan semantic verification, and timing always use the target database.
`--comparison-mode both` (default) compares Original with PGPlan and OuterYan.
`pgplan-only` (`--skip1`) omits the OuterYan result comparison. `none`
(`--skip2`, `--performance-only`, `--performance_only`, or the compatibility
misspelling `--performace_only`) runs target EXPLAIN and performance only, using
the persistent plan cache without requiring a prior correctness receipt.
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
        --correctness-from)
            [ $# -ge 2 ] || die "$1 requires a value"
            CORRECTNESS_FROM="$2"
            shift 2
            ;;
        --reuse-from)
            [ $# -ge 2 ] || die "$1 requires a value"
            REUSE_FROM="$2"
            shift 2
            ;;
        --plan-cache)
            [ $# -ge 2 ] || die "$1 requires a value"
            PLAN_CACHE="$2"
            shift 2
            ;;
        --comparison-mode)
            [ $# -ge 2 ] || die "$1 requires a value"
            COMPARISON_MODE="$2"
            shift 2
            ;;
        --skip1)
            COMPARISON_MODE="pgplan-only"
            shift
            ;;
        --skip2|--performance-only|--performance_only|--performace_only)
            COMPARISON_MODE="none"
            shift
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
case "$COMPARISON_MODE" in
    both|pgplan-only|none) ;;
    *) die "--comparison-mode must be both, pgplan-only, or none" ;;
esac
[[ "$LIMIT" =~ ^[0-9]+$ ]] || die "--limit must be a non-negative integer"
[[ "$ROW_CAP" =~ ^[1-9][0-9]*$ ]] || die "--rows must be a positive integer"
if [ -n "$REUSE_FROM" ]; then
    CORRECTNESS_MODE="reuse"
    CORRECTNESS_FROM="$REUSE_FROM"
fi
case "$CORRECTNESS_MODE" in
    target|bounded|reuse) ;;
    *) die "--correctness-mode must be target, bounded, or reuse" ;;
esac
if [ "$CORRECTNESS_MODE" = "reuse" ]; then
    [ -n "$CORRECTNESS_FROM" ] || \
        die "--correctness-from is required with --correctness-mode reuse"
    [ -d "$CORRECTNESS_FROM" ] || \
        die "correctness reuse corpus does not exist: $CORRECTNESS_FROM"
    CORRECTNESS_FROM="$(cd -P -- "$CORRECTNESS_FROM" && printf '%s\n' "$PWD")"
    if [ -n "$REUSE_FROM" ]; then
        REUSE_FROM="$CORRECTNESS_FROM"
    fi
    [ "$CORRECTNESS_FROM" != "/" ] || \
        die "refusing to use the filesystem root as a correctness corpus"
    [ -d "$CORRECTNESS_FROM/runs" ] || \
        die "correctness reuse corpus has no runs directory: $CORRECTNESS_FROM"
    REUSE_RUNS_ROOT="$(cd -P -- "$CORRECTNESS_FROM/runs" && printf '%s\n' "$PWD")"
    case "$REUSE_RUNS_ROOT" in
        "$CORRECTNESS_FROM"/*) ;;
        *) die "unsafe correctness reuse runs path escapes its corpus root: $REUSE_RUNS_ROOT" ;;
    esac
else
    REUSE_RUNS_ROOT=""
fi
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
if [[ "$PYTHON_BIN" == */* ]]; then
    [ -x "$PYTHON_BIN" ] || die "Python binary is not executable: $PYTHON_BIN"
else
    command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "Python binary was not found: $PYTHON_BIN"
fi

for helper in experiment.sh summarize_corpus.sh; do
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
if [ -e "$PLAN_CACHE" ] && [ ! -d "$PLAN_CACHE" ]; then
    die "--plan-cache is not a directory: $PLAN_CACHE"
fi
mkdir -p "$PLAN_CACHE"
PLAN_CACHE="$(cd "$PLAN_CACHE" && pwd -P)"
[ "$PLAN_CACHE" != "/" ] || die "refusing to use the filesystem root as --plan-cache"
if [ "$CORRECTNESS_MODE" = "reuse" ]; then
    case "$OUT/" in
        "$CORRECTNESS_FROM/"*) die "--out must not be inside the correctness reuse corpus: $OUT" ;;
    esac
    case "$CORRECTNESS_FROM/" in
        "$OUT/"*) die "correctness reuse corpus must not be inside --out: $CORRECTNESS_FROM" ;;
    esac
fi
mkdir -p "$OUT/artifacts" "$OUT/runs" "$OUT/logs" "$OUT/data_manifests" \
    "$OUT/correctness_dbs" "$OUT/query_snapshots" "$OUT/cache_plan_snapshots"
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
    echo "ERROR: could not format comparison result row $row_number (exit=$formatter_rc)" >&2
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

schema_for_family() {
    case "$1" in
        graph) printf '%s' pgplan_graph ;;
        tpch) printf '%s' public ;;
        tpcds) printf '%s' pgplan_tpcds ;;
        job) printf '%s' pgplan_job ;;
        *) return 2 ;;
    esac
}

plan_data_for_family() {
    case "$1" in
        graph) printf 'graph-duckdb-sample-%s' "$ROW_CAP" ;;
        tpch) printf '%s' tpch-sf0.01 ;;
        tpcds) printf 'tpcds-duckdb-sample-%s' "$ROW_CAP" ;;
        job) printf 'job-duckdb-sample-%s' "$ROW_CAP" ;;
        *) return 2 ;;
    esac
}

tables_for_family() {
    case "$1" in
        graph) printf '%s\n' r1 r2 r3 r4 r5 r6 r7 r8 r9 r10 ;;
        tpcds)
            printf '%s\n' \
                call_center catalog_page catalog_returns catalog_sales customer \
                customer_address customer_demographics date_dim \
                household_demographics income_band inventory item promotion reason \
                ship_mode store store_returns store_sales time_dim warehouse \
                web_page web_returns web_sales web_site
            ;;
        job)
            printf '%s\n' \
                aka_name aka_title cast_info char_name comp_cast_type company_name \
                company_type complete_cast info_type keyword kind_type link_type \
                movie_companies movie_info movie_info_idx movie_keyword movie_link \
                name person_info role_type title
            ;;
        *) return 2 ;;
    esac
}

plan_sample_sha_for_family() {
    case "$1" in
        graph) printf '%s' "$PLAN_SAMPLE_SHA_GRAPH" ;;
        tpch) printf '%s' "$PLAN_SAMPLE_SHA_TPCH" ;;
        tpcds) printf '%s' "$PLAN_SAMPLE_SHA_TPCDS" ;;
        job) printf '%s' "$PLAN_SAMPLE_SHA_JOB" ;;
        *) return 2 ;;
    esac
}

plan_sample_error_for_family() {
    case "$1" in
        graph) printf '%s' "$PLAN_SAMPLE_ERROR_GRAPH" ;;
        tpch) printf '%s' "$PLAN_SAMPLE_ERROR_TPCH" ;;
        tpcds) printf '%s' "$PLAN_SAMPLE_ERROR_TPCDS" ;;
        job) printf '%s' "$PLAN_SAMPLE_ERROR_JOB" ;;
        *) return 2 ;;
    esac
}

stats_epoch_for_family() {
    case "$1" in
        graph) printf '%s' "$STATS_EPOCH_GRAPH" ;;
        tpch) printf '%s' "$STATS_EPOCH_TPCH" ;;
        tpcds) printf '%s' "$STATS_EPOCH_TPCDS" ;;
        job) printf '%s' "$STATS_EPOCH_JOB" ;;
        *) return 2 ;;
    esac
}

set_stats_epoch_for_family() {
    local family="$1" epoch="$2"
    case "$family" in
        graph) STATS_EPOCH_GRAPH="$epoch" ;;
        tpch) STATS_EPOCH_TPCH="$epoch" ;;
        tpcds) STATS_EPOCH_TPCDS="$epoch" ;;
        job) STATS_EPOCH_JOB="$epoch" ;;
        *) return 2 ;;
    esac
}

create_stats_epoch() {
    local family="$1" sample_sha epoch_file epoch
    sample_sha="$(plan_sample_sha_for_family "$family")" || return 1
    epoch_file="$OUT/data_manifests/${family}_stats_epoch.tsv"
    {
        printf 'format\tduckyan.pgplan_stats_epoch.v1\n'
        printf 'family\t%s\n' "$family"
        printf 'plan_sample_sha256\t%s\n' "$sample_sha"
        printf 'created_utc\t%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        printf 'process_nonce\t%s-%s-%s\n' "$$" "$RANDOM" "$RANDOM"
    } > "$epoch_file" || return 1
    epoch="$(sha256_file "$epoch_file")" || return 1
    set_stats_epoch_for_family "$family" "$epoch"
    printf 'stats_epoch_%s\t%s\n' "$family" "$epoch" >> "$RUN_CONFIG_TSV"
}

set_plan_sample_result() {
    local family="$1" digest="$2" error="$3"
    case "$family" in
        graph) PLAN_SAMPLE_SHA_GRAPH="$digest"; PLAN_SAMPLE_ERROR_GRAPH="$error" ;;
        tpch) PLAN_SAMPLE_SHA_TPCH="$digest"; PLAN_SAMPLE_ERROR_TPCH="$error" ;;
        tpcds) PLAN_SAMPLE_SHA_TPCDS="$digest"; PLAN_SAMPLE_ERROR_TPCDS="$error" ;;
        job) PLAN_SAMPLE_SHA_JOB="$digest"; PLAN_SAMPLE_ERROR_JOB="$error" ;;
        *) return 2 ;;
    esac
}

# Hash exactly the inputs used to construct the PostgreSQL planning sample:
# For sampled families, hash schema/constraint metadata and the deterministic
# physical rowid range [0, ROW_CAP). TPC-H hashes every canonically ordered
# SF0.01 row plus its schema/loader recipe. The target-scale database file is
# never hashed merely to validate the plan cache.
fingerprint_plan_sample() {
    local family="$1" family_db="$2" manifest="$3" work_dir section_file section_header
    local section_sha table table_in="" metadata_sql constraints_sql data_sql digest
    local sample_rows schema_sha loader_sha generator_db spec order
    local tables=()

    if [ "$family" = "tpch" ]; then
        work_dir="$(mktemp -d "$OUT/.plan_sample_tpch.XXXXXX")" || return 1
        schema_sha="$(sha256_file "$SCRIPT_DIR/tpch_schema.sql")" || {
            rm -rf -- "$work_dir"
            return 1
        }
        loader_sha="$(sha256_file "$SCRIPT_DIR/prepare_tpch_pg.sh")" || {
            rm -rf -- "$work_dir"
            return 1
        }
        {
            printf 'format\tduckyan.pgplan_sample_identity.v1\n'
            printf 'family\ttpch\n'
            printf 'plan_data\ttpch-sf0.01\n'
            printf 'recipe\tduckdb_tpch_dbgen_sf_0.01\n'
            printf 'schema_sha256\t%s\n' "$schema_sha"
            printf 'loader_sha256\t%s\n' "$loader_sha"
            printf 'statistics_recipe\tpostgres_analyze_defaults_v1\n'
            printf 'postgres_version_num\t160002\n'
        } > "$manifest" || {
            rm -rf -- "$work_dir"
            return 1
        }
        generator_db="$work_dir/tpch_sf001.duckdb"
        if ! "$DUCKDB_BIN" "$generator_db" -no-init -bail \
                -c "CALL dbgen(sf=0.01);" > "$work_dir/dbgen.log" 2>&1; then
            rm -rf -- "$work_dir"
            return 1
        fi
        for spec in \
                region:r_regionkey nation:n_nationkey supplier:s_suppkey \
                customer:c_custkey part:p_partkey \
                partsupp:ps_partkey,ps_suppkey orders:o_orderkey \
                lineitem:l_orderkey,l_linenumber; do
            table="${spec%%:*}"
            order="${spec#*:}"
            section_file="$work_dir/$table.csv"
            if ! "$DUCKDB_BIN" "$generator_db" -no-init -bail -csv -noheader \
                    -c "SELECT * FROM \"$table\" ORDER BY $order;" \
                    > "$section_file"; then
                rm -rf -- "$work_dir"
                return 1
            fi
            section_sha="$(sha256_file "$section_file")" || {
                rm -rf -- "$work_dir"
                return 1
            }
            printf 'section\t%s\t%s\n' "$table" "$section_sha" >> "$manifest" || {
                rm -rf -- "$work_dir"
                return 1
            }
        done
        PLAN_SAMPLE_RESULT="$(sha256_file "$manifest")" || {
            rm -rf -- "$work_dir"
            return 1
        }
        rm -rf -- "$work_dir"
        return 0
    fi

    while IFS= read -r table; do
        [ -n "$table" ] || continue
        tables+=("$table")
        if [ -n "$table_in" ]; then
            table_in="$table_in,"
        fi
        table_in="$table_in'$table'"
    done < <(tables_for_family "$family")
    [ "${#tables[@]}" -gt 0 ] || return 1

    work_dir="$(mktemp -d "$OUT/.plan_sample_${family}.XXXXXX")" || return 1
    loader_sha="$(sha256_file "$SCRIPT_DIR/prepare_sampled_pg.sh")" || {
        rm -rf -- "$work_dir"
        return 1
    }
    schema_sha="$(sha256_file "$SCRIPT_DIR/schema_from_duckdb.py")" || {
        rm -rf -- "$work_dir"
        return 1
    }
    {
        printf 'format\tduckyan.pgplan_sample_identity.v1\n'
        printf 'family\t%s\n' "$family"
        printf 'plan_data\t%s\n' "$(plan_data_for_family "$family")"
        printf 'row_cap\t%s\n' "$ROW_CAP"
        printf 'recipe\tduckdb_rowid_prefix_csv_v1\n'
        printf 'loader_sha256\t%s\n' "$loader_sha"
        printf 'schema_converter_sha256\t%s\n' "$schema_sha"
    } > "$manifest" || {
        rm -rf -- "$work_dir"
        return 1
    }

    metadata_sql="
        SELECT table_name, column_name, data_type, is_nullable, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'main' AND lower(table_name) IN ($table_in)
        ORDER BY lower(table_name), ordinal_position"
    constraints_sql="
        SELECT c.table_name, c.constraint_index, c.constraint_type,
               unnest(c.constraint_column_names) AS column_name,
               generate_subscripts(c.constraint_column_names, 1) AS column_ordinal
        FROM duckdb_constraints() c
        WHERE c.schema_name = 'main'
          AND lower(c.table_name) IN ($table_in)
          AND c.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
        ORDER BY lower(c.table_name), c.constraint_index, column_ordinal"

    for table in __metadata__ __constraints__ "${tables[@]}"; do
        section_file="$work_dir/$table.csv"
        case "$table" in
            __metadata__) data_sql="$metadata_sql" ;;
            __constraints__) data_sql="$constraints_sql" ;;
            *)
                sample_rows="$({
                    "$DUCKDB_BIN" "$family_db" -no-init -bail -csv -noheader -c \
                        "SELECT count(*) FROM \"$table\"
                         WHERE rowid >= 0 AND rowid < $ROW_CAP;"
                } | tr -d '[:space:]')" || {
                    rm -rf -- "$work_dir"
                    return 1
                }
                case "$sample_rows" in
                    ''|*[!0-9]*) rm -rf -- "$work_dir"; return 1 ;;
                esac
                printf 'rows\t%s\t%s\n' "$table" "$sample_rows" >> "$manifest"
                data_sql="SELECT * FROM \"$table\"
                          WHERE rowid >= 0 AND rowid < $ROW_CAP
                          ORDER BY rowid"
                ;;
        esac
        section_header=-header
        case "$table" in
            __metadata__|__constraints__) ;;
            *) section_header=-noheader ;;
        esac
        if ! "$DUCKDB_BIN" "$family_db" -no-init -bail -csv "$section_header" \
                -c "$data_sql" > "$section_file"; then
            rm -rf -- "$work_dir"
            return 1
        fi
        section_sha="$(sha256_file "$section_file")" || {
            rm -rf -- "$work_dir"
            return 1
        }
        printf 'section\t%s\t%s\n' "$table" "$section_sha" >> "$manifest" || {
            rm -rf -- "$work_dir"
            return 1
        }
    done
    digest="$(sha256_file "$manifest")" || {
        rm -rf -- "$work_dir"
        return 1
    }
    rm -rf -- "$work_dir"
    PLAN_SAMPLE_RESULT="$digest"
}

cache_path_for_query() {
    local relative="$1"
    printf '%s/%s.pg.json' "$PLAN_CACHE" "${relative%.sql}"
}

cache_identity_path() {
    printf '%s.plan_sample.sha256' "$1"
}

cache_stats_epoch() {
    awk -F '=' '$1 == "stats_epoch" {print $2; exit}' "$1"
}

# Cache entries are data, not trusted control input. Require a regular file
# physically below the configured cache root, exact query provenance, the
# pinned PostgreSQL version/data identity, and a well-formed typed binary tree.
# A stale or malformed entry is only a cache miss; fresh capture replaces it.
validate_cached_plan() {
    local candidate="$1" identity="$2" query="$3" family="$4" expected_sample_sha="$5"
    local allowed_root="${6:-$PLAN_CACHE}"
    local expected_stats_epoch="${7:-}"
    local resolved identity_resolved schema plan_data artifact_sha
    [ -f "$candidate" ] && [ ! -L "$candidate" ] || {
        echo "cache candidate is absent or not a regular non-symlink file: $candidate" >&2
        return 1
    }
    [ -f "$identity" ] && [ ! -L "$identity" ] || {
        echo "cache identity is absent or not a regular non-symlink file: $identity" >&2
        return 1
    }
    resolved="$("$PYTHON_BIN" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$candidate")" || return 1
    identity_resolved="$("$PYTHON_BIN" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$identity")" || return 1
    case "$resolved" in
        "$allowed_root"/*) ;;
        *) echo "cache candidate escapes configured root: $candidate -> $resolved" >&2; return 1 ;;
    esac
    case "$identity_resolved" in
        "$allowed_root"/*) ;;
        *) echo "cache identity escapes configured root: $identity -> $identity_resolved" >&2; return 1 ;;
    esac
    schema="$(schema_for_family "$family")" || return 1
    plan_data="$(plan_data_for_family "$family")" || return 1
    artifact_sha="$(sha256_file "$resolved")" || return 1
    "$PYTHON_BIN" -c '
import hashlib
import json
import re
import sys

script_dir, artifact_path, identity_path, query_path, expected_schema, expected_data, expected_sample_sha, artifact_sha, expected_stats_epoch = sys.argv[1:]
sys.path.insert(0, script_dir)
from normalize_plan import (FORMAT, QUERY_CANONICALIZATION, SUPPORTED_VERSION,
                            canonicalize_query)

with open(artifact_path, "r", encoding="utf-8") as source:
    artifact = json.load(source)
with open(query_path, "rb") as source:
    query_sha = hashlib.sha256(canonicalize_query(source.read())).hexdigest()
if artifact.get("format") != FORMAT:
    raise ValueError("format mismatch")
if artifact.get("query_sha256") != query_sha:
    raise ValueError("query SHA-256 mismatch")
if artifact.get("query_sha256_canonicalization") != QUERY_CANONICALIZATION:
    raise ValueError("query canonicalization mismatch")
postgres = artifact.get("postgres")
if not isinstance(postgres, dict):
    raise ValueError("postgres provenance is missing")
if postgres.get("version_num") != SUPPORTED_VERSION:
    raise ValueError("PostgreSQL version mismatch")
if postgres.get("plan_schema") != expected_schema:
    raise ValueError("plan schema mismatch")
if postgres.get("plan_data") != expected_data:
    raise ValueError("plan data mismatch")
expected_settings = {"max_parallel_workers_per_gather": "0"}
if expected_schema != "public":
    expected_settings["search_path"] = "{}, pg_catalog".format(expected_schema)
if postgres.get("settings") != expected_settings:
    raise ValueError("PostgreSQL settings mismatch")

identity = {}
with open(identity_path, "r", encoding="utf-8") as source:
    for number, line in enumerate(source.read().splitlines(), 1):
        key, separator, value = line.partition("=")
        if not separator or not key or key in identity:
            raise ValueError("malformed cache identity line {}".format(number))
        identity[key] = value
stats_epoch = identity.get("stats_epoch", "")
if not re.match(r"^[0-9a-f]{64}$", stats_epoch):
    raise ValueError("cache statistics epoch is invalid")
if expected_stats_epoch and stats_epoch != expected_stats_epoch:
    raise ValueError("cache statistics epoch mismatch")
if identity != {
    "format": "duckyan.pgplan_cache_identity.v2",
    "artifact_sha256": artifact_sha,
    "family": expected_data.split("-", 1)[0],
    "plan_data": expected_data,
    "plan_sample_sha256": expected_sample_sha,
    "stats_epoch": stats_epoch,
}:
    raise ValueError("cache plan-selection identity mismatch")

leaves = set()
aliases = set()
def visit(node):
    if not isinstance(node, dict):
        raise ValueError("tree node is not an object")
    op = node.get("op")
    if op == "scan":
        schema = node.get("schema")
        relation = node.get("relation")
        alias = node.get("alias")
        occurrence = node.get("occurrence")
        if not all(isinstance(value, str) and value for value in (schema, relation, alias)):
            raise ValueError("scan identity is incomplete")
        if schema.casefold() != "public":
            raise ValueError("scan schema must use canonical PostgreSQL public identity")
        if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 0:
            raise ValueError("scan occurrence is invalid")
        identity = (schema.casefold(), relation.casefold(), occurrence)
        if identity in leaves or alias.casefold() in aliases:
            raise ValueError("scan identity or alias is duplicated")
        leaves.add(identity)
        aliases.add(alias.casefold())
        return 1, 0
    if op != "join" or node.get("join_type") not in ("inner", "left", "right", "full"):
        raise ValueError("join node is invalid")
    left_leaves, left_joins = visit(node.get("left"))
    right_leaves, right_joins = visit(node.get("right"))
    return left_leaves + right_leaves, left_joins + right_joins + 1

leaf_count, join_count = visit(artifact.get("tree"))
if leaf_count < 1 or join_count != leaf_count - 1:
    raise ValueError("tree is not connected and binary")
' "$SCRIPT_DIR" "$resolved" "$identity_resolved" "$query" "$schema" "$plan_data" \
        "$expected_sample_sha" "$artifact_sha" "$expected_stats_epoch"
}

publish_plan_cache() {
    local source="$1" destination="$2" query="$3" family="$4" sample_sha="$5" stats_epoch="$6"
    local parent parent_real temporary identity_temporary base artifact_sha identity_destination
    parent="$(dirname "$destination")"
    base="$(basename "$destination")"
    mkdir -p "$parent" || return 1
    parent_real="$(cd -P -- "$parent" && printf '%s\n' "$PWD")" || return 1
    case "$parent_real" in
        "$PLAN_CACHE"|"$PLAN_CACHE"/*) ;;
        *) echo "cache destination escapes configured root: $destination" >&2; return 1 ;;
    esac
    temporary="$(mktemp "$parent_real/.${base}.tmp.XXXXXX")" || return 1
    identity_temporary="$(mktemp "$parent_real/.${base}.identity.tmp.XXXXXX")" || {
        rm -f -- "$temporary"
        return 1
    }
    identity_destination="$(cache_identity_path "$destination")"
    if ! cp -- "$source" "$temporary"; then
        rm -f -- "$temporary" "$identity_temporary"
        return 1
    fi
    artifact_sha="$(sha256_file "$temporary")" || {
        rm -f -- "$temporary" "$identity_temporary"
        return 1
    }
    {
        printf 'format=duckyan.pgplan_cache_identity.v2\n'
        printf 'artifact_sha256=%s\n' "$artifact_sha"
        printf 'family=%s\n' "$family"
        printf 'plan_data=%s\n' "$(plan_data_for_family "$family")"
        printf 'plan_sample_sha256=%s\n' "$sample_sha"
        printf 'stats_epoch=%s\n' "$stats_epoch"
    } > "$identity_temporary" || {
        rm -f -- "$temporary" "$identity_temporary"
        return 1
    }
    if ! validate_cached_plan "$temporary" "$identity_temporary" "$query" "$family" \
            "$sample_sha" "$PLAN_CACHE" "$stats_epoch"; then
        rm -f -- "$temporary" "$identity_temporary"
        return 1
    fi
    # Publish the artifact first. Until the matching identity is installed,
    # concurrent readers see an artifact-hash mismatch and safely treat it as a
    # miss; they can never accept an old plan under a new sample identity.
    if ! "$PYTHON_BIN" -c 'import os,sys; os.replace(sys.argv[1], sys.argv[2])' \
            "$temporary" "$destination" || \
            ! "$PYTHON_BIN" -c 'import os,sys; os.replace(sys.argv[1], sys.argv[2])' \
                "$identity_temporary" "$identity_destination"; then
        rm -f -- "$temporary" "$identity_temporary"
        return 1
    fi
}

# A database hash is meaningful only after DuckDB has checkpointed its WAL.
# Check both the configured spelling and the real file target so a database
# symlink cannot hide pending changes beside its destination. An empty stale
# regular WAL is harmless; any non-empty or non-regular WAL fails closed.
check_target_database_wal() {
    local family="$1" path="$2" real_path wal
    real_path="$("$PYTHON_BIN" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$path")" || {
        echo "could not resolve the $family target database: $path" >&2
        return 1
    }
    [ -f "$real_path" ] || {
        echo "$family target database does not resolve to a regular file: $path" >&2
        return 1
    }
    for wal in "$path.wal" "$real_path.wal"; do
        [ ! -e "$wal" ] || [ -f "$wal" ] || {
            echo "$family target database has an unsafe active WAL path: $wal" >&2
            return 1
        }
        [ ! -s "$wal" ] || {
            echo "$family target database has a non-empty WAL; checkpoint it before testing: $wal" >&2
            return 1
        }
    done
}

fingerprint_target_database() {
    local family="$1" path="$2" real_path digest
    real_path="$("$PYTHON_BIN" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$path")" || {
        echo "could not resolve the $family target database: $path" >&2
        return 1
    }
    check_target_database_wal "$family" "$path" || return 1
    digest="$(sha256_file "$real_path")" || return 1
    # Catch a writer that created or populated the WAL while hashing.
    check_target_database_wal "$family" "$path" || return 1
    case "$family" in
        graph) TARGET_DB_SHA_GRAPH="$digest" ;;
        tpch) TARGET_DB_SHA_TPCH="$digest" ;;
        tpcds) TARGET_DB_SHA_TPCDS="$digest" ;;
        job) TARGET_DB_SHA_JOB="$digest" ;;
        *) return 2 ;;
    esac
    printf '[comparison] fingerprint %s target DB: %s\n' "$family" "$digest"
}

target_db_sha_for_family() {
    case "$1" in
        graph) printf '%s' "$TARGET_DB_SHA_GRAPH" ;;
        tpch) printf '%s' "$TARGET_DB_SHA_TPCH" ;;
        tpcds) printf '%s' "$TARGET_DB_SHA_TPCDS" ;;
        job) printf '%s' "$TARGET_DB_SHA_JOB" ;;
        *) return 2 ;;
    esac
}

set_target_db_sha_for_family() {
    local family="$1" digest="$2"
    case "$family" in
        graph) TARGET_DB_SHA_GRAPH="$digest" ;;
        tpch) TARGET_DB_SHA_TPCH="$digest" ;;
        tpcds) TARGET_DB_SHA_TPCDS="$digest" ;;
        job) TARGET_DB_SHA_JOB="$digest" ;;
        *) return 2 ;;
    esac
}

# Resolve only the exact runs/FAMILY/LABEL directory. `cd -P` follows all
# directory symlinks, after which the containment check rejects an escape from
# the prior corpus. experiment.sh performs the cryptographic receipt checks.
resolve_reuse_query_run() {
    local family="$1" label="$2" candidate resolved
    candidate="$REUSE_RUNS_ROOT/$family/$label"
    if [ ! -d "$candidate" ]; then
        REUSE_FAILURE_DETAIL="missing prior per-query run directory: $candidate"
        return 1
    fi
    resolved="$(cd -P -- "$candidate" && printf '%s\n' "$PWD")" || {
        REUSE_FAILURE_DETAIL="could not resolve prior per-query run directory: $candidate"
        return 1
    }
    case "$resolved" in
        "$REUSE_RUNS_ROOT"/*) ;;
        *)
            REUSE_FAILURE_DETAIL="unsafe prior per-query run path escapes corpus: $candidate -> $resolved"
            return 1
            ;;
    esac
    if [ ! -f "$resolved/correctness/receipt.txt" ] || \
            [ -L "$resolved/correctness/receipt.txt" ]; then
        REUSE_FAILURE_DETAIL="missing sealed correctness receipt: $resolved/correctness/receipt.txt"
        return 1
    fi
    REUSE_QUERY_RUN="$resolved"
}

resolve_contained_prior_file() {
    local candidate="$1" resolved
    resolved="$("$PYTHON_BIN" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$candidate")" || {
        PLAN_REUSE_FAILURE_DETAIL="could not resolve prior file: $candidate"
        return 1
    }
    case "$resolved" in
        "$CORRECTNESS_FROM"/*) ;;
        *)
            PLAN_REUSE_FAILURE_DETAIL="unsafe prior file escapes corpus: $candidate -> $resolved"
            return 1
            ;;
    esac
    [ -f "$resolved" ] || {
        PLAN_REUSE_FAILURE_DETAIL="prior path is not a regular file: $candidate"
        return 1
    }
    RESOLVED_PRIOR_FILE="$resolved"
}

resolve_reuse_plan() {
    local family="$1" label="$2" primary fallback
    primary="$CORRECTNESS_FROM/artifacts/$family/$label.pg.json"
    fallback="$REUSE_RUNS_ROOT/$family/$label/provenance/postgres_plan.json"
    if [ -e "$primary" ] || [ -L "$primary" ]; then
        resolve_contained_prior_file "$primary" || return 1
    elif [ -e "$fallback" ] || [ -L "$fallback" ]; then
        resolve_contained_prior_file "$fallback" || return 1
    else
        PLAN_REUSE_FAILURE_DETAIL="missing prior PGPlan artifact (checked $primary and $fallback)"
        return 1
    fi
    REUSE_PLAN_SOURCE="$RESOLVED_PRIOR_FILE"
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
        echo "ERROR: comparison corpus report generation failed (exit=$summary_rc; log=$summary_log)" >&2
    fi

    echo "[comparison] complete: selected=${#QUERY_PATHS[@]} completed=$pass_count skip=$skip_count fail=$fail_count status=$STATUS_TSV"
    echo "[comparison] reports: comparison_tsv=$OUT/comparison.tsv comparison_csv=$OUT/comparison.csv comparison_log=$OUT/comparison.log summary_tsv=$OUT/summary.tsv failures_tsv=$OUT/failures.tsv"
    [ "$FAILED" -eq 0 ]
}

QUERY_CACHE_HITS=()
QUERY_CACHE_PATHS=()
QUERY_CACHE_SNAPSHOTS=()
QUERY_CACHE_IDENTITY_SNAPSHOTS=()
QUERY_CACHE_STATS_EPOCHS=()
NEED_PG_SETUP=0
PLAN_SAMPLE_SHA_GRAPH=""
PLAN_SAMPLE_SHA_TPCH=""
PLAN_SAMPLE_SHA_TPCDS=""
PLAN_SAMPLE_SHA_JOB=""
PLAN_SAMPLE_ERROR_GRAPH=""
PLAN_SAMPLE_ERROR_TPCH=""
PLAN_SAMPLE_ERROR_TPCDS=""
PLAN_SAMPLE_ERROR_JOB=""
PLAN_SAMPLE_FAILURE=0
RECACHE_GRAPH=0
RECACHE_TPCH=0
RECACHE_TPCDS=0
RECACHE_JOB=0
CACHE_EPOCH_GRAPH=""
CACHE_EPOCH_TPCH=""
CACHE_EPOCH_TPCDS=""
CACHE_EPOCH_JOB=""
STATS_EPOCH_GRAPH=""
STATS_EPOCH_TPCH=""
STATS_EPOCH_TPCDS=""
STATS_EPOCH_JOB=""

mark_family_recache() {
    case "$1" in
        graph) RECACHE_GRAPH=1 ;;
        tpch) RECACHE_TPCH=1 ;;
        tpcds) RECACHE_TPCDS=1 ;;
        job) RECACHE_JOB=1 ;;
        *) return 2 ;;
    esac
}

family_needs_recache() {
    case "$1" in
        graph) [ "$RECACHE_GRAPH" -eq 1 ] ;;
        tpch) [ "$RECACHE_TPCH" -eq 1 ] ;;
        tpcds) [ "$RECACHE_TPCDS" -eq 1 ] ;;
        job) [ "$RECACHE_JOB" -eq 1 ] ;;
        *) return 2 ;;
    esac
}

register_cache_epoch() {
    local family="$1" epoch="$2" seen
    case "$family" in
        graph) seen="$CACHE_EPOCH_GRAPH" ;;
        tpch) seen="$CACHE_EPOCH_TPCH" ;;
        tpcds) seen="$CACHE_EPOCH_TPCDS" ;;
        job) seen="$CACHE_EPOCH_JOB" ;;
        *) return 2 ;;
    esac
    if [ -n "$seen" ] && [ "$seen" != "$epoch" ]; then
        mark_family_recache "$family"
        return 0
    fi
    case "$family" in
        graph) CACHE_EPOCH_GRAPH="$epoch" ;;
        tpch) CACHE_EPOCH_TPCH="$epoch" ;;
        tpcds) CACHE_EPOCH_TPCDS="$epoch" ;;
        job) CACHE_EPOCH_JOB="$epoch" ;;
    esac
}
if [ -z "$REUSE_FROM" ]; then
    [ -r "$SCRIPT_DIR/normalize_plan.py" ] || \
        die "query normalizer is not readable: $SCRIPT_DIR/normalize_plan.py"
    for family in "${FAMILIES[@]}"; do
        family_selected=0
        for selected_family in "${QUERY_FAMILIES[@]}"; do
            [ "$selected_family" != "$family" ] || family_selected=1
        done
        [ "$family_selected" -eq 1 ] || continue
        family_db="$(db_for_family "$family")" || die "unknown family: $family"
        sample_manifest="$OUT/data_manifests/${family}_plan_sample.tsv"
        sample_log="$OUT/logs/fingerprint_plan_sample_$family.log"
        PLAN_SAMPLE_RESULT=""
        if fingerprint_plan_sample "$family" "$family_db" "$sample_manifest" \
                > "$sample_log" 2>&1 && \
                [[ "$PLAN_SAMPLE_RESULT" =~ ^[0-9a-f]{64}$ ]]; then
            set_plan_sample_result "$family" "$PLAN_SAMPLE_RESULT" ""
            printf '[pgplan] plan sample fingerprint %s: %s\n' \
                "$family" "$PLAN_SAMPLE_RESULT"
        else
            sample_detail="$(sanitize_detail "$sample_log")"
            set_plan_sample_result "$family" "" "$sample_detail"
            PLAN_SAMPLE_FAILURE=1
            printf '[pgplan] plan sample fingerprint failed for %s: %s\n' \
                "$family" "$sample_detail" >&2
        fi
    done

    printf 'family\tquery\tcache_path\tstatus\tplan_sample_sha256\tdetail\n' > "$OUT/plan_cache.tsv"
    for index in "${!QUERY_PATHS[@]}"; do
        family="${QUERY_FAMILIES[$index]}"
        query="${QUERY_PATHS[$index]}"
        relative="${QUERY_RELATIVES[$index]}"
        label="${QUERY_LABELS[$index]}"
        cache_path="$(cache_path_for_query "$relative")"
        cache_identity="$(cache_identity_path "$cache_path")"
        cache_snapshot="$OUT/cache_plan_snapshots/${relative%.sql}.pg.json"
        cache_identity_snapshot="$(cache_identity_path "$cache_snapshot")"
        cache_log="$OUT/logs/${family}__${label}__cache.log"
        sample_sha="$(plan_sample_sha_for_family "$family")"
        QUERY_CACHE_PATHS[$index]="$cache_path"
        QUERY_CACHE_SNAPSHOTS[$index]=""
        QUERY_CACHE_IDENTITY_SNAPSHOTS[$index]=""
        QUERY_CACHE_STATS_EPOCHS[$index]=""
        if [ -z "$sample_sha" ]; then
            QUERY_CACHE_HITS[$index]=0
            sample_detail="$(plan_sample_error_for_family "$family")"
            printf '%s\t%s\t%s\tUNAVAILABLE\t\t%s\n' \
                "$family" "$relative" "$cache_path" "$sample_detail" >> "$OUT/plan_cache.tsv"
            continue
        fi
        if validate_cached_plan "$cache_path" "$cache_identity" "$query" "$family" \
                "$sample_sha" \
                > "$cache_log" 2>&1; then
            cache_epoch="$(cache_stats_epoch "$cache_identity")"
            mkdir -p "$(dirname "$cache_snapshot")"
            if cp -- "$cache_path" "$cache_snapshot" && \
                    cp -- "$cache_identity" "$cache_identity_snapshot" && \
                    validate_cached_plan "$cache_snapshot" "$cache_identity_snapshot" \
                        "$query" "$family" "$sample_sha" \
                        "$OUT/cache_plan_snapshots" "$cache_epoch" \
                        >> "$cache_log" 2>&1; then
                QUERY_CACHE_HITS[$index]=1
                QUERY_CACHE_SNAPSHOTS[$index]="$cache_snapshot"
                QUERY_CACHE_IDENTITY_SNAPSHOTS[$index]="$cache_identity_snapshot"
                QUERY_CACHE_STATS_EPOCHS[$index]="$cache_epoch"
                register_cache_epoch "$family" "$cache_epoch"
                printf '%s\t%s\t%s\tHIT\t%s\tvalidated query, artifact, and plan sample\n' \
                    "$family" "$relative" "$cache_path" "$sample_sha" >> "$OUT/plan_cache.tsv"
                continue
            fi
            printf '%s\n' "cache candidate changed or could not be snapshotted" >> "$cache_log"
        fi
        QUERY_CACHE_HITS[$index]=0
        mark_family_recache "$family"
        NEED_PG_SETUP=1
        cache_detail="$(sanitize_detail "$cache_log")"
        printf '%s\t%s\t%s\tMISS\t%s\t%s\n' \
            "$family" "$relative" "$cache_path" "$sample_sha" "$cache_detail" >> "$OUT/plan_cache.tsv"
    done

    # Plans selected under different ANALYZE samples are not a coherent
    # optimizer baseline. If any selected query in a family is missing/stale,
    # or otherwise carries a different statistics epoch, recapture every
    # selected plan in that family under one newly prepared epoch.
    for index in "${!QUERY_PATHS[@]}"; do
        family="${QUERY_FAMILIES[$index]}"
        [ "${QUERY_CACHE_HITS[$index]:-0}" -eq 1 ] || continue
        if family_needs_recache "$family"; then
            relative="${QUERY_RELATIVES[$index]}"
            cache_path="${QUERY_CACHE_PATHS[$index]}"
            sample_sha="$(plan_sample_sha_for_family "$family")"
            QUERY_CACHE_HITS[$index]=0
            QUERY_CACHE_SNAPSHOTS[$index]=""
            QUERY_CACHE_IDENTITY_SNAPSHOTS[$index]=""
            QUERY_CACHE_STATS_EPOCHS[$index]=""
            NEED_PG_SETUP=1
            printf '%s\t%s\t%s\tRECACHE\t%s\tselected family requires one coherent statistics epoch\n' \
                "$family" "$relative" "$cache_path" "$sample_sha" >> "$OUT/plan_cache.tsv"
        fi
    done
fi

echo "[comparison] selected ${#QUERY_PATHS[@]} query(s); status=$STATUS_TSV"
echo "[comparison] comparison mode=$COMPARISON_MODE correctness mode=$CORRECTNESS_MODE${CORRECTNESS_FROM:+ source=$CORRECTNESS_FROM}"
echo "[comparison] persistent PGPlan cache=$PLAN_CACHE"
DUCKDB_BIN_SHA256="$(sha256_file "$DUCKDB_BIN")" || \
    die "could not fingerprint the DuckDB binary: $DUCKDB_BIN"
TARGET_DB_SHA_GRAPH=""
TARGET_DB_SHA_TPCH=""
TARGET_DB_SHA_TPCDS=""
TARGET_DB_SHA_JOB=""
COLLECT_TARGET_DB_SHA=0
if [ "$CORRECTNESS_MODE" = "reuse" ] || \
        { [ "$COMPARISON_MODE" = "both" ] && [ "$CORRECTNESS_MODE" = "target" ]; }; then
    COLLECT_TARGET_DB_SHA=1
fi
RUN_CONFIG_TSV="$OUT/run_config.tsv"
{
    printf 'key\tvalue\n'
    printf 'correctness_mode\t%s\n' "$CORRECTNESS_MODE"
    printf 'correctness_from\t%s\n' "$CORRECTNESS_FROM"
    printf 'comparison_mode\t%s\n' "$COMPARISON_MODE"
    printf 'plan_cache\t%s\n' "$PLAN_CACHE"
    printf 'plan_reuse_from\t%s\n' "$REUSE_FROM"
    printf 'duckdb_bin\t%s\n' "$DUCKDB_BIN"
    printf 'duckdb_bin_sha256\t%s\n' "$DUCKDB_BIN_SHA256"
} > "$RUN_CONFIG_TSV"
if [ -z "$REUSE_FROM" ]; then
    for family in "${FAMILIES[@]}"; do
        sample_sha="$(plan_sample_sha_for_family "$family")"
        [ -z "$sample_sha" ] || \
            printf 'plan_sample_%s_sha256\t%s\n' "$family" "$sample_sha" >> "$RUN_CONFIG_TSV"
    done
fi
if [ -n "$REUSE_FROM" ]; then
    printf 'family\tquery\tprior_plan\tcopied_plan\n' > "$OUT/plan_reuse_sources.tsv"
fi
printf '[comparison] fingerprint DuckDB binary: %s\n' "$DUCKDB_BIN_SHA256"
SETUP_LOG="$OUT/logs/setup_pg.log"
PG_SETUP_FAILED=0
PG_SETUP_FAILURE_DETAIL=""
if [ -n "$REUSE_FROM" ]; then
    printf '[comparison] certified reuse of prior PGPlan artifacts; PostgreSQL setup is not run\n' | tee "$SETUP_LOG"
elif [ "$NEED_PG_SETUP" -eq 0 ] && [ "$PLAN_SAMPLE_FAILURE" -eq 1 ]; then
    printf '[comparison] plan-sample fingerprinting failed; PostgreSQL setup cannot repair those queries and is not run\n' | tee "$SETUP_LOG"
elif [ "$NEED_PG_SETUP" -eq 0 ]; then
    printf '[comparison] all selected PGPlan artifacts hit the persistent cache; PostgreSQL setup is not run\n' | tee "$SETUP_LOG"
else
    if [ -z "$PG_DSN" ]; then
        PG_SETUP_FAILED=1
        PG_SETUP_FAILURE_DETAIL="--pg-dsn is required for cache misses (or set PG_DSN)"
        printf '%s\n' "$PG_SETUP_FAILURE_DETAIL" > "$SETUP_LOG"
    else
        for helper in setup_pg.sh prepare_sampled_pg.sh make_plan.sh; do
            if [ ! -x "$SCRIPT_DIR/$helper" ]; then
                PG_SETUP_FAILED=1
                PG_SETUP_FAILURE_DETAIL="required cache-miss helper is not executable: $SCRIPT_DIR/$helper"
                printf '%s\n' "$PG_SETUP_FAILURE_DETAIL" > "$SETUP_LOG"
                break
            fi
        done
    fi
    if [ "$PG_SETUP_FAILED" -eq 0 ] && \
            ! bash "$SCRIPT_DIR/setup_pg.sh" > "$SETUP_LOG" 2>&1; then
        PG_SETUP_FAILED=1
        PG_SETUP_FAILURE_DETAIL="$(sanitize_detail "$SETUP_LOG")"
    fi
    if [ "$PG_SETUP_FAILED" -eq 1 ]; then
        echo "ERROR: PostgreSQL setup failed for cache misses: $PG_SETUP_FAILURE_DETAIL" >&2
    fi
fi

PREPARED_GRAPH=0
PREPARED_TPCH=0
PREPARED_TPCDS=0
PREPARED_JOB=0
CURRENT_SCHEMA=""
CURRENT_PLAN_DATA=""
CURRENT_CORRECTNESS_DB=""
CURRENT_EXECUTION_DB_SHA256=""

prepare_family() {
    local family="$1" family_db correctness_db correctness_log correctness_rows
    local correctness_manifest correctness_fingerprints correctness_db_sha correctness_manifest_sha
    local fingerprint_log target_db_sha
    local correctness_args=()
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
    fingerprint_log="$OUT/logs/fingerprint_target_$family.log"
    if [ "$COLLECT_TARGET_DB_SHA" -eq 1 ]; then
        if ! fingerprint_target_database "$family" "$family_db" > "$fingerprint_log" 2>&1; then
            PREPARE_FAILURE_DETAIL="$(sanitize_detail "$fingerprint_log")"
            return 1
        fi
        cat "$fingerprint_log"
    else
        if ! check_target_database_wal "$family" "$family_db" > "$fingerprint_log" 2>&1; then
            PREPARE_FAILURE_DETAIL="$(sanitize_detail "$fingerprint_log")"
            return 1
        fi
        set_target_db_sha_for_family "$family" NOT_COLLECTED
        printf '[comparison] %s target DB SHA-256: NOT_COLLECTED (no reusable correctness receipt)\n' \
            "$family" | tee -a "$fingerprint_log"
    fi
    target_db_sha="$(target_db_sha_for_family "$family")" || {
        PREPARE_FAILURE_DETAIL="could not retrieve the $family target database fingerprint"
        return 1
    }
    {
        printf 'target_db_%s\t%s\n' "$family" "$family_db"
        printf 'target_db_%s_sha256\t%s\n' "$family" "$target_db_sha"
    } >> "$RUN_CONFIG_TSV"
    if [ -n "$REUSE_FROM" ]; then
        CURRENT_CORRECTNESS_DB="$family_db"
        case "$family" in
            graph) PREPARED_GRAPH=1 ;;
            tpch) PREPARED_TPCH=1 ;;
            tpcds) PREPARED_TPCDS=1 ;;
            job) PREPARED_JOB=1 ;;
        esac
        return 0
    fi
    if [ "$CORRECTNESS_MODE" = "bounded" ] && [ "$COMPARISON_MODE" != "none" ]; then
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

    case "$family" in
        graph) PREPARED_GRAPH=1 ;;
        tpch) PREPARED_TPCH=1 ;;
        tpcds) PREPARED_TPCDS=1 ;;
        job) PREPARED_JOB=1 ;;
    esac
    return 0
}

PG_PREPARED_GRAPH=0
PG_PREPARED_TPCH=0
PG_PREPARED_TPCDS=0
PG_PREPARED_JOB=0
PG_PREPARE_ERROR_GRAPH=""
PG_PREPARE_ERROR_TPCH=""
PG_PREPARE_ERROR_TPCDS=""
PG_PREPARE_ERROR_JOB=""

prepare_capture_family() {
    local family="$1" family_db prepare_log state error
    local force_args=()
    case "$family" in
        graph) state="$PG_PREPARED_GRAPH"; error="$PG_PREPARE_ERROR_GRAPH" ;;
        tpch) state="$PG_PREPARED_TPCH"; error="$PG_PREPARE_ERROR_TPCH" ;;
        tpcds) state="$PG_PREPARED_TPCDS"; error="$PG_PREPARE_ERROR_TPCDS" ;;
        job) state="$PG_PREPARED_JOB"; error="$PG_PREPARE_ERROR_JOB" ;;
        *) return 2 ;;
    esac
    if [ "$state" -eq 1 ]; then
        return 0
    fi
    if [ "$state" -eq 2 ]; then
        CAPTURE_PREP_FAILURE_DETAIL="$error"
        return 1
    fi
    if [ "$PG_SETUP_FAILED" -eq 1 ]; then
        CAPTURE_PREP_FAILURE_DETAIL="$PG_SETUP_FAILURE_DETAIL"
        return 1
    fi

    # Rebuild the pinned TPC-H data for every new statistics epoch. This avoids
    # accepting an arbitrary same-cardinality public schema and ensures every
    # selected TPC-H artifact in this recapture batch sees one ANALYZE snapshot.
    if [ "$family" = "tpch" ]; then
        prepare_log="$OUT/logs/prepare_pg_tpch.log"
        if [ ! -x "$SCRIPT_DIR/prepare_tpch_pg.sh" ]; then
            CAPTURE_PREP_FAILURE_DETAIL="required TPC-H preparation helper is not executable: $SCRIPT_DIR/prepare_tpch_pg.sh"
            PG_PREPARED_TPCH=2
            PG_PREPARE_ERROR_TPCH="$CAPTURE_PREP_FAILURE_DETAIL"
            return 1
        fi
        echo "[pgplan] rebuild canonical PostgreSQL TPC-H SF0.01 plan-selection data"
        if bash "$SCRIPT_DIR/prepare_tpch_pg.sh" \
                --pg-dsn "$PG_DSN" --duckdb-bin "$DUCKDB_BIN" --force \
                > "$prepare_log" 2>&1; then
            if create_stats_epoch tpch; then
                PG_PREPARED_TPCH=1
                return 0
            fi
            CAPTURE_PREP_FAILURE_DETAIL="could not record the TPC-H PostgreSQL statistics epoch"
        else
            CAPTURE_PREP_FAILURE_DETAIL="$(sanitize_detail "$prepare_log")"
        fi
        PG_PREPARED_TPCH=2
        PG_PREPARE_ERROR_TPCH="$CAPTURE_PREP_FAILURE_DETAIL"
        return 1
    fi

    family_db="$(db_for_family "$family")" || return 2
    prepare_log="$OUT/logs/prepare_pg_$family.log"
    echo "[pgplan] prepare minimal PostgreSQL $family plan-selection data"
    if [ "${PGPLAN_SETUP:-${PG_REPLAY_SETUP:-source}}" != "external" ] || \
            [ "${PGPLAN_FORCE_SAMPLED_DATA:-${PGPLAN_FORCE_DATA:-${PG_REPLAY_FORCE_DATA:-0}}}" = "1" ]; then
        force_args=(--force)
    fi
    if bash "$SCRIPT_DIR/prepare_sampled_pg.sh" \
            --family "$family" \
            --duckdb-db "$family_db" \
            --pg-dsn "$PG_DSN" \
            --rows "$ROW_CAP" \
            --manifest "$OUT/data_manifests/$family.tsv" \
            "${force_args[@]}" > "$prepare_log" 2>&1; then
        if create_stats_epoch "$family"; then
            case "$family" in
                graph) PG_PREPARED_GRAPH=1 ;;
                tpcds) PG_PREPARED_TPCDS=1 ;;
                job) PG_PREPARED_JOB=1 ;;
            esac
            return 0
        fi
        CAPTURE_PREP_FAILURE_DETAIL="could not record the $family PostgreSQL statistics epoch"
    else
        CAPTURE_PREP_FAILURE_DETAIL="$(sanitize_detail "$prepare_log")"
    fi

    case "$family" in
        graph) PG_PREPARED_GRAPH=2; PG_PREPARE_ERROR_GRAPH="$CAPTURE_PREP_FAILURE_DETAIL" ;;
        tpcds) PG_PREPARED_TPCDS=2; PG_PREPARE_ERROR_TPCDS="$CAPTURE_PREP_FAILURE_DETAIL" ;;
        job) PG_PREPARED_JOB=2; PG_PREPARE_ERROR_JOB="$CAPTURE_PREP_FAILURE_DETAIL" ;;
    esac
    return 1
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
    printf '[comparison] query %d/%d: %s\n' \
        "$((index + 1))" "${#QUERY_PATHS[@]}" "$relative"
    printf '%s\n' "$QUERY_SEPARATOR"
    sample_sha=""
    if [ -z "$REUSE_FROM" ]; then
        sample_sha="$(plan_sample_sha_for_family "$family")"
        if [ -z "$sample_sha" ]; then
            detail="$(plan_sample_error_for_family "$family")"
            record_query_status "$((index + 1))" \
                "$family" "$relative" FAIL plan_sample "$detail" "" ""
            echo "[pgplan] FAIL $relative (plan sample fingerprint: $detail)" >&2
            FAILED=1
            continue
        fi
        if [ "${QUERY_CACHE_HITS[$index]:-0}" -eq 0 ] && \
                [ "$PG_SETUP_FAILED" -eq 1 ]; then
            record_query_status "$((index + 1))" \
                "$family" "$relative" FAIL setup "$PG_SETUP_FAILURE_DETAIL" "" ""
            echo "[pgplan] FAIL $relative (PostgreSQL setup: $PG_SETUP_FAILURE_DETAIL)" >&2
            FAILED=1
            continue
        fi
    fi
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
            if [ "$CORRECTNESS_MODE" = "bounded" ] && [ "$COMPARISON_MODE" != "none" ]; then
                CURRENT_CORRECTNESS_DB="$OUT/correctness_dbs/graph.duckdb"
            else
                CURRENT_CORRECTNESS_DB="$(db_for_family graph)"
            fi
            CURRENT_EXECUTION_DB_SHA256="$TARGET_DB_SHA_GRAPH"
            ;;
        tpch)
            CURRENT_SCHEMA="public"
            CURRENT_PLAN_DATA="tpch-sf0.01"
            if [ "$CORRECTNESS_MODE" = "bounded" ] && [ "$COMPARISON_MODE" != "none" ]; then
                CURRENT_CORRECTNESS_DB="$OUT/correctness_dbs/tpch.duckdb"
            else
                CURRENT_CORRECTNESS_DB="$(db_for_family tpch)"
            fi
            CURRENT_EXECUTION_DB_SHA256="$TARGET_DB_SHA_TPCH"
            ;;
        tpcds)
            CURRENT_SCHEMA="pgplan_tpcds"
            CURRENT_PLAN_DATA="tpcds-duckdb-sample-$ROW_CAP"
            if [ "$CORRECTNESS_MODE" = "bounded" ] && [ "$COMPARISON_MODE" != "none" ]; then
                CURRENT_CORRECTNESS_DB="$OUT/correctness_dbs/tpcds.duckdb"
            else
                CURRENT_CORRECTNESS_DB="$(db_for_family tpcds)"
            fi
            CURRENT_EXECUTION_DB_SHA256="$TARGET_DB_SHA_TPCDS"
            ;;
        job)
            CURRENT_SCHEMA="pgplan_job"
            CURRENT_PLAN_DATA="job-duckdb-sample-$ROW_CAP"
            if [ "$CORRECTNESS_MODE" = "bounded" ] && [ "$COMPARISON_MODE" != "none" ]; then
                CURRENT_CORRECTNESS_DB="$OUT/correctness_dbs/job.duckdb"
            else
                CURRENT_CORRECTNESS_DB="$(db_for_family job)"
            fi
            CURRENT_EXECUTION_DB_SHA256="$TARGET_DB_SHA_JOB"
            ;;
    esac

    REUSE_QUERY_RUN=""
    if [ "$CORRECTNESS_MODE" = "reuse" ]; then
        if ! resolve_reuse_query_run "$family" "$label"; then
            record_query_status "$((index + 1))" \
                "$family" "$relative" FAIL reuse_correctness "$REUSE_FAILURE_DETAIL" "" ""
            echo "[comparison] FAIL $relative (correctness reuse: $REUSE_FAILURE_DETAIL)" >&2
            FAILED=1
            continue
        fi
    fi

    plan_dir="$OUT/artifacts/$family"
    result_dir="$OUT/runs/$family/$label"
    mkdir -p "$plan_dir" "$(dirname "$result_dir")"
    plan="$plan_dir/$label.pg.json"
    capture_log="$OUT/logs/${family}__${label}__capture.log"
    experiment_log="$OUT/logs/${family}__${label}__experiment.log"
    captured_fresh=0

    if [ -z "$REUSE_FROM" ] && [ "${QUERY_CACHE_HITS[$index]:-0}" -eq 0 ]; then
        if ! prepare_capture_family "$family"; then
            record_query_status "$((index + 1))" \
                "$family" "$relative" FAIL prepare_plan_data \
                "$CAPTURE_PREP_FAILURE_DETAIL" "" ""
            echo "[pgplan] FAIL $relative (plan-data preparation: $CAPTURE_PREP_FAILURE_DETAIL)" >&2
            FAILED=1
            continue
        fi
    fi

    if [ -n "$REUSE_FROM" ]; then
        if ! resolve_reuse_plan "$family" "$label"; then
            record_query_status "$((index + 1))" \
                "$family" "$relative" FAIL reuse_plan "$PLAN_REUSE_FAILURE_DETAIL" "" ""
            echo "[pgplan] FAIL $relative (plan reuse: $PLAN_REUSE_FAILURE_DETAIL)" >&2
            FAILED=1
            continue
        fi
        if ! cp -- "$REUSE_PLAN_SOURCE" "$plan"; then
            detail="could not copy prior PGPlan artifact: $REUSE_PLAN_SOURCE"
            record_query_status "$((index + 1))" \
                "$family" "$relative" FAIL reuse_plan "$detail" "" ""
            echo "[pgplan] FAIL $relative (plan reuse: $detail)" >&2
            FAILED=1
            continue
        fi
        printf '%s\t%s\t%s\t%s\n' \
            "$family" "$relative" "$REUSE_PLAN_SOURCE" "$plan" \
            >> "$OUT/plan_reuse_sources.tsv"
        printf '[pgplan] reuse %s from %s\n' "$relative" "$REUSE_PLAN_SOURCE"
        printf 'reused_plan=%s\n' "$REUSE_PLAN_SOURCE" > "$capture_log"
        capture_rc=0
    elif [ "${QUERY_CACHE_HITS[$index]:-0}" -eq 1 ]; then
        cache_snapshot="${QUERY_CACHE_SNAPSHOTS[$index]}"
        cache_identity_snapshot="${QUERY_CACHE_IDENTITY_SNAPSHOTS[$index]}"
        cache_path="${QUERY_CACHE_PATHS[$index]}"
        if cp -- "$cache_snapshot" "$plan" && \
                cp -- "$cache_identity_snapshot" "$(cache_identity_path "$plan")"; then
            capture_rc=0
            printf '[pgplan] cache hit %s from %s\n' "$relative" "$cache_path"
            printf 'cached_plan=%s\ncache_snapshot=%s\n' \
                "$cache_path" "$cache_snapshot" > "$capture_log"
        else
            capture_rc=2
            printf 'could not copy validated cache snapshot: %s\n' \
                "$cache_snapshot" > "$capture_log"
        fi
    else
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
        [ "$capture_rc" -ne 0 ] || captured_fresh=1
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
    if [ "$captured_fresh" -eq 1 ]; then
        # The source DuckDB sample is read before PostgreSQL preparation and
        # again after EXPLAIN capture. A concurrent schema/prefix mutation can
        # never publish an artifact under the earlier sample identity.
        post_sample_manifest="$OUT/data_manifests/${family}__${label}__plan_sample_post.tsv"
        post_sample_log="$OUT/logs/${family}__${label}__plan_sample_post.log"
        PLAN_SAMPLE_RESULT=""
        if ! fingerprint_plan_sample "$family" "$(db_for_family "$family")" \
                "$post_sample_manifest" > "$post_sample_log" 2>&1; then
            detail="$(sanitize_detail "$post_sample_log")"
            record_query_status "$((index + 1))" \
                "$family" "$relative" FAIL plan_sample_changed "$detail" "$plan" ""
            printf '[pgplan] FAIL %s (post-capture plan sample fingerprint: %s)\n' \
                "$relative" "$detail" >&2
            FAILED=1
            continue
        fi
        if [ "$PLAN_SAMPLE_RESULT" != "$sample_sha" ]; then
            detail="plan-selection sample changed during capture: before=$sample_sha after=$PLAN_SAMPLE_RESULT"
            record_query_status "$((index + 1))" \
                "$family" "$relative" FAIL plan_sample_changed "$detail" "$plan" ""
            printf '[pgplan] FAIL %s (%s)\n' "$relative" "$detail" >&2
            FAILED=1
            continue
        fi
        stats_epoch="$(stats_epoch_for_family "$family")"
        if ! [[ "$stats_epoch" =~ ^[0-9a-f]{64}$ ]]; then
            detail="missing or invalid PostgreSQL statistics epoch after plan capture"
            record_query_status "$((index + 1))" \
                "$family" "$relative" FAIL plan_cache "$detail" "$plan" ""
            printf '[pgplan] FAIL %s (%s)\n' "$relative" "$detail" >&2
            FAILED=1
            continue
        fi
        cache_path="${QUERY_CACHE_PATHS[$index]}"
        cache_publish_log="$OUT/logs/${family}__${label}__cache_publish.log"
        if publish_plan_cache "$plan" "$cache_path" "$query" "$family" "$sample_sha" \
                "$stats_epoch" \
                > "$cache_publish_log" 2>&1 && \
                cp -- "$(cache_identity_path "$cache_path")" \
                    "$(cache_identity_path "$plan")" >> "$cache_publish_log" 2>&1; then
            printf '[pgplan] cached %s at %s\n' "$relative" "$cache_path"
            printf '%s\t%s\t%s\tPUBLISHED\t%s\tfresh capture atomically installed\n' \
                "$family" "$relative" "$cache_path" "$sample_sha" >> "$OUT/plan_cache.tsv"
        else
            detail="$(sanitize_detail "$cache_publish_log")"
            printf '%s\t%s\t%s\tPUBLISH_FAILED\t%s\t%s\n' \
                "$family" "$relative" "$cache_path" "$sample_sha" "$detail" >> "$OUT/plan_cache.tsv"
            record_query_status "$((index + 1))" \
                "$family" "$relative" FAIL plan_cache "$detail" "$plan" ""
            printf '[pgplan] FAIL %s (could not publish persistent plan cache: %s)\n' \
                "$relative" "$detail" >&2
            FAILED=1
            continue
        fi
    fi

    execution_db="$(db_for_family "$family")"
    wal_log="$OUT/logs/${family}__${label}__wal_check.log"
    if ! check_target_database_wal "$family" "$execution_db" > "$wal_log" 2>&1; then
        detail="$(sanitize_detail "$wal_log")"
        record_query_status "$((index + 1))" \
            "$family" "$relative" FAIL provenance "$detail" "$plan" ""
        echo "[comparison] FAIL $relative (target database WAL: $detail)" >&2
        FAILED=1
        continue
    fi
    [ -n "$CURRENT_EXECUTION_DB_SHA256" ] || {
        record_query_status "$((index + 1))" \
            "$family" "$relative" FAIL provenance \
            "missing target database fingerprint state" "$plan" ""
        FAILED=1
        continue
    }
    experiment_extra_args=(
        --duckdb-bin-sha256 "$DUCKDB_BIN_SHA256"
        --comparison-mode "$COMPARISON_MODE"
    )
    if [[ "$CURRENT_EXECUTION_DB_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
        experiment_extra_args+=(--execution-db-sha256 "$CURRENT_EXECUTION_DB_SHA256")
    elif [ "$CURRENT_EXECUTION_DB_SHA256" != "NOT_COLLECTED" ]; then
        record_query_status "$((index + 1))" \
            "$family" "$relative" FAIL provenance \
            "invalid target database fingerprint state: $CURRENT_EXECUTION_DB_SHA256" "$plan" ""
        FAILED=1
        continue
    fi
    if [ "$CORRECTNESS_MODE" = "reuse" ]; then
        experiment_extra_args+=(--reuse-correctness-from "$REUSE_QUERY_RUN")
    fi
    echo "[comparison] execute $relative (mode=$COMPARISON_MODE correctness=$CORRECTNESS_MODE-$family${REUSE_QUERY_RUN:+ from=$REUSE_QUERY_RUN}; target EXPLAIN/timing; per-step timeout=${TIMEOUT_SECS}s; log=$experiment_log)"
    if PGPLAN_TIMEOUT_SECS="$TIMEOUT_SECS" \
            PGPLAN_TIMEOUT_GRACE="${PGPLAN_TIMEOUT_GRACE:-${OY_BATCH_GRACE_SECS:-30}}" \
            PGPLAN_TMPDIR="${PGPLAN_TMPDIR:-${OY_TMPDIR:-$OUT/tmp}}" \
            PGPLAN_KEEP_CORRECTNESS_FILES="${PGPLAN_KEEP_CORRECTNESS_FILES:-0}" \
            bash "$SCRIPT_DIR/experiment.sh" \
                --duckdb-bin "$DUCKDB_BIN" \
                --execution-db "$execution_db" \
                --correctness-db "$CURRENT_CORRECTNESS_DB" \
                "${experiment_extra_args[@]}" \
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
    if [ "$CORRECTNESS_MODE" = "bounded" ] && [ "$COMPARISON_MODE" != "none" ]; then
        provenance_log="$OUT/logs/${family}__${label}__correctness_provenance.log"
        if ! attach_correctness_provenance "$family" "$result_dir" \
                > "$provenance_log" 2>&1; then
            detail="$(sanitize_detail "$provenance_log")"
            record_query_status "$((index + 1))" \
                "$family" "$relative" FAIL provenance "$detail" "$plan" "$result_dir"
            echo "[comparison] FAIL $relative (provenance: $detail)" >&2
            FAILED=1
            continue
        fi
    fi
    if [ "$experiment_rc" -eq 124 ]; then
        detail="$(sanitize_detail "$experiment_log")"
        record_query_status "$((index + 1))" \
            "$family" "$relative" SKIP execute_timeout "$detail" "$plan" "$result_dir"
        echo "[comparison] SKIP $relative (execution timeout: $detail)"
        FAILED=1
        continue
    fi
    if [ "$experiment_rc" -ne 0 ]; then
        detail="$(sanitize_detail "$experiment_log")"
        record_query_status "$((index + 1))" \
            "$family" "$relative" FAIL execute "$detail" "$plan" "$result_dir"
        echo "[comparison] FAIL $relative (execute: $detail)" >&2
        FAILED=1
        continue
    fi

    record_query_status "$((index + 1))" \
        "$family" "$relative" PASS complete \
        "complete comparison_mode=$COMPARISON_MODE correctness_mode=$CORRECTNESS_MODE" "$plan" "$result_dir"
    echo "[comparison] PASS $relative"
done

finalize_rc=0
finalize_corpus || finalize_rc=$?
exit "$finalize_rc"
