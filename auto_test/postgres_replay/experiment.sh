#!/usr/bin/env bash
# Compare DuckDB's native join tree, PostgreSQL's logical tree (PGPlan), and
# OuterYan. Requested correctness runs before timing and executes the bare
# query; ordering is normalized only after DuckDB has emitted complete CSV.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CSV_RECORDS="$SCRIPT_DIR/csv_records.py"
NORMALIZER="$SCRIPT_DIR/normalize_plan.py"

usage() {
	cat <<'EOF'
Usage: experiment.sh [options]

Required (each also has the environment fallback shown):
  --duckdb-bin PATH   DuckDB CLI (DUCKDB_BIN)
  --execution-db PATH Target-scale DuckDB database (PGPLAN_EXECUTION_DB)
  --query PATH        File containing one result-producing SQL query
                      (PGPLAN_QUERY)
  --plan PATH         duckyan.pg_join_tree.v1 artifact (PGPLAN_PLAN)
  --out PATH          Output directory (PGPLAN_OUT)

Optional:
  --correctness-db PATH
                      DuckDB database used only for requested exact multiset
                      checks (PGPLAN_CORRECTNESS_DB; default: execution DB)
  --comparison-mode MODE
                      Fresh correctness work: both, pgplan-only, or none
                      (PGPLAN_COMPARISON_MODE; default: both). All modes still
                      run settings, EXPLAIN, PGPlan verification, and TM.
  --reuse-correctness-from PATH
                      Performance-only mode: reuse a sealed, target-scale
                      correctness receipt from a prior per-query experiment
                      directory (PGPLAN_REUSE_CORRECTNESS_FROM). The receipt
                      is validated fail-closed; default is fresh correctness.
  --execution-db-sha256 SHA256
                      Precomputed target database SHA-256
                      (PGPLAN_EXECUTION_DB_SHA256; otherwise computed locally)
  --duckdb-bin-sha256 SHA256
                      Precomputed DuckDB binary SHA-256
                      (PGPLAN_DUCKDB_BIN_SHA256; otherwise computed locally)
  --runs N            Positive odd TM measured-run count after one warm-up
                      (PGPLAN_RUNS, default: 3).
  --threads N         Positive DuckDB thread count
                      (PGPLAN_THREADS, default: 16; run_all.sh sweeps 16/32)
  -h, --help          Show this help

Optional environment controls:
  PGPLAN_TIMEOUT_SECS  Per-DuckDB-statement and per-correctness-postprocessing
                       step timeout in seconds; 0 disables (direct-script
                       default: 0)
  PGPLAN_TIMEOUT_GRACE Extra timing-batch watchdog grace (default: 30)
  PGPLAN_TMPDIR        Parent directory for temporary files (default: TMPDIR)
  PGPLAN_KEEP_CORRECTNESS_FILES
                       Keep large CSV/JSONL correctness files (default: 1).
                       Corpus orchestration sets 0 after recording their hash.
  PYTHON_BIN              Python 3 used for standard-library CSV framing
                          (default: python3; no pip packages)

The output directory always receives plans, traces, settings, timing logs, and
copies/hashes of the query and PostgreSQL artifact. Correctness result artifacts
depend on --comparison-mode or a validated reuse receipt.
TM uses DuckDB CLI `.timer` real wall-clock samples of the fully drained
bare query in `.mode trash`; result serialization and filesystem output are not
charged to the query-execution benchmark.
EOF
}

die() {
	printf 'experiment.sh: %s\n' "$*" >&2
	exit 1
}

usage_error() {
	printf 'experiment.sh: %s\n\n' "$*" >&2
	usage >&2
	exit 2
}

require_value() {
	[ "$#" -ge 2 ] && [ -n "$2" ] || usage_error "$1 requires a value"
}

DUCKDB_BIN="${DUCKDB_BIN:-}"
EXECUTION_DB="${PGPLAN_EXECUTION_DB:-${PG_REPLAY_EXECUTION_DB:-}}"
CORRECTNESS_DB="${PGPLAN_CORRECTNESS_DB:-}"
COMPARISON_MODE="${PGPLAN_COMPARISON_MODE:-both}"
REUSE_CORRECTNESS_FROM="${PGPLAN_REUSE_CORRECTNESS_FROM:-}"
EXECUTION_DB_SHA256="${PGPLAN_EXECUTION_DB_SHA256:-}"
DUCKDB_BIN_SHA256="${PGPLAN_DUCKDB_BIN_SHA256:-}"
QUERY_PATH="${PGPLAN_QUERY:-${PG_REPLAY_QUERY:-}}"
PLAN_PATH="${PGPLAN_PLAN:-${PG_REPLAY_PLAN:-}}"
OUT_DIR="${PGPLAN_OUT:-${PG_REPLAY_OUT:-}}"
RUNS="${PGPLAN_RUNS:-${PG_REPLAY_RUNS:-3}}"
THREADS="${PGPLAN_THREADS:-${PG_REPLAY_THREADS:-16}}"
TIMEOUT_SECS="${PGPLAN_TIMEOUT_SECS:-${PG_REPLAY_TIMEOUT_SECS:-0}}"
TIMEOUT_GRACE="${PGPLAN_TIMEOUT_GRACE:-${PG_REPLAY_TIMEOUT_GRACE:-30}}"
KEEP_CORRECTNESS_FILES="${PGPLAN_KEEP_CORRECTNESS_FILES:-1}"

while [ "$#" -gt 0 ]; do
	case "$1" in
		--duckdb-bin)
			require_value "$@"; DUCKDB_BIN="$2"; shift 2 ;;
		--execution-db)
			require_value "$@"; EXECUTION_DB="$2"; shift 2 ;;
		--correctness-db)
			require_value "$@"; CORRECTNESS_DB="$2"; shift 2 ;;
		--comparison-mode)
			require_value "$@"; COMPARISON_MODE="$2"; shift 2 ;;
		--reuse-correctness-from)
			require_value "$@"; REUSE_CORRECTNESS_FROM="$2"; shift 2 ;;
		--execution-db-sha256)
			require_value "$@"; EXECUTION_DB_SHA256="$2"; shift 2 ;;
		--duckdb-bin-sha256)
			require_value "$@"; DUCKDB_BIN_SHA256="$2"; shift 2 ;;
		--query)
			require_value "$@"; QUERY_PATH="$2"; shift 2 ;;
		--plan)
			require_value "$@"; PLAN_PATH="$2"; shift 2 ;;
		--runs)
			require_value "$@"; RUNS="$2"; shift 2 ;;
		--threads)
			require_value "$@"; THREADS="$2"; shift 2 ;;
		--out)
			require_value "$@"; OUT_DIR="$2"; shift 2 ;;
		-h|--help)
			usage; exit 0 ;;
		--)
			shift; [ "$#" -eq 0 ] || usage_error "unexpected positional arguments: $*" ;;
		-*)
			usage_error "unknown option: $1" ;;
		*)
			usage_error "unexpected positional argument: $1" ;;
	esac
done

[ -n "$DUCKDB_BIN" ] || usage_error "--duckdb-bin is required"
[ -n "$EXECUTION_DB" ] || usage_error "--execution-db is required"
[ -n "$CORRECTNESS_DB" ] || CORRECTNESS_DB="$EXECUTION_DB"
[ -n "$QUERY_PATH" ] || usage_error "--query is required"
[ -n "$PLAN_PATH" ] || usage_error "--plan is required"
[ -n "$OUT_DIR" ] || usage_error "--out is required"

case "$RUNS" in ''|*[!0-9]*|0) usage_error "--runs must be a positive integer" ;; esac
[ $((RUNS % 2)) -eq 1 ] || usage_error "--runs must be odd"
case "$THREADS" in ''|*[!0-9]*|0) usage_error "--threads must be a positive integer" ;; esac
case "$TIMEOUT_SECS" in ''|*[!0-9]*) usage_error "PGPLAN_TIMEOUT_SECS must be a non-negative integer" ;; esac
case "$TIMEOUT_GRACE" in ''|*[!0-9]*) usage_error "PGPLAN_TIMEOUT_GRACE must be a non-negative integer" ;; esac
case "$KEEP_CORRECTNESS_FILES" in 0|1) ;; *) usage_error "PGPLAN_KEEP_CORRECTNESS_FILES must be 0 or 1" ;; esac
case "$COMPARISON_MODE" in
	both|pgplan-only|none) ;;
	*) usage_error "--comparison-mode must be both, pgplan-only, or none" ;;
esac
case "$EXECUTION_DB_SHA256" in ''|*[!0-9a-fA-F]*)
	[ -z "$EXECUTION_DB_SHA256" ] || usage_error "--execution-db-sha256 must be exactly 64 hexadecimal characters" ;;
esac
[ -z "$EXECUTION_DB_SHA256" ] || [ "${#EXECUTION_DB_SHA256}" -eq 64 ] || \
	usage_error "--execution-db-sha256 must be exactly 64 hexadecimal characters"
case "$DUCKDB_BIN_SHA256" in ''|*[!0-9a-fA-F]*)
	[ -z "$DUCKDB_BIN_SHA256" ] || usage_error "--duckdb-bin-sha256 must be exactly 64 hexadecimal characters" ;;
esac
[ -z "$DUCKDB_BIN_SHA256" ] || [ "${#DUCKDB_BIN_SHA256}" -eq 64 ] || \
	usage_error "--duckdb-bin-sha256 must be exactly 64 hexadecimal characters"

[ -x "$DUCKDB_BIN" ] || die "DuckDB binary is not executable: $DUCKDB_BIN"
[ -f "$EXECUTION_DB" ] || die "execution database does not exist: $EXECUTION_DB"
[ -f "$CORRECTNESS_DB" ] || die "correctness database does not exist: $CORRECTNESS_DB"
[ -r "$QUERY_PATH" ] || die "query file is not readable: $QUERY_PATH"
[ -r "$PLAN_PATH" ] || die "plan artifact is not readable: $PLAN_PATH"
[ -z "$REUSE_CORRECTNESS_FROM" ] || [ -d "$REUSE_CORRECTNESS_FROM" ] || \
	die "correctness reuse source is not a directory: $REUSE_CORRECTNESS_FROM"
if [[ "$PYTHON_BIN" == */* ]]; then
	[ -x "$PYTHON_BIN" ] || die "Python binary is not executable: $PYTHON_BIN"
else
	command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "Python 3 is required: $PYTHON_BIN"
fi
[ -r "$CSV_RECORDS" ] || die "CSV record helper is not readable: $CSV_RECORDS"
[ -r "$NORMALIZER" ] || die "query normalizer is not readable: $NORMALIZER"

# Resolve input paths once. This both permits relative arguments and ensures
# the internal plan variable remains valid after the script changes directories.
canonical_file() {
	local path="$1" dir base
	dir="$(dirname -- "$path")"
	base="$(basename -- "$path")"
	(
		cd -P -- "$dir"
		printf '%s/%s\n' "$PWD" "$base"
	)
}

DUCKDB_BIN="$(canonical_file "$DUCKDB_BIN")"
EXECUTION_DB="$(canonical_file "$EXECUTION_DB")"
CORRECTNESS_DB="$(canonical_file "$CORRECTNESS_DB")"
QUERY_PATH="$(canonical_file "$QUERY_PATH")"
PLAN_PATH="$(canonical_file "$PLAN_PATH")"
if [ -n "$REUSE_CORRECTNESS_FROM" ]; then
	REUSE_CORRECTNESS_FROM="$(cd -P -- "$REUSE_CORRECTNESS_FROM" && printf '%s\n' "$PWD")"
	[ "$CORRECTNESS_DB" = "$EXECUTION_DB" ] || \
		die "correctness reuse requires the correctness database to be the target execution database"
fi
NEED_EXECUTION_DB_SHA256=0
if [ -n "$REUSE_CORRECTNESS_FROM" ] || \
		{ [ "$COMPARISON_MODE" = "both" ] && [ "$CORRECTNESS_DB" = "$EXECUTION_DB" ]; }; then
	NEED_EXECUTION_DB_SHA256=1
fi
case "$DUCKDB_BIN" in
	*debug*) printf 'experiment.sh: warning: debug-build timings are directional only\n' >&2 ;;
esac
mkdir -p -- "$OUT_DIR"
OUT_DIR="$(cd -P -- "$OUT_DIR" && printf '%s\n' "$PWD")"

if [ -n "$(find "$OUT_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
	die "--out must name an empty directory: $OUT_DIR"
fi

mkdir -p -- "$OUT_DIR/plans" "$OUT_DIR/correctness" "$OUT_DIR/traces" \
	"$OUT_DIR/settings" "$OUT_DIR/timing" "$OUT_DIR/provenance" "$OUT_DIR/checks"

TMP_PARENT="${PGPLAN_TMPDIR:-${PG_REPLAY_TMPDIR:-${TMPDIR:-/tmp}}}"
mkdir -p -- "$TMP_PARENT"
TMP_PARENT="$(cd -P -- "$TMP_PARENT" && printf '%s\n' "$PWD")"
WORK_DIR="$(mktemp -d "$TMP_PARENT/duckyan_pgplan.XXXXXX")" || die "cannot create temporary directory"

cleanup() {
	local rc=$?
	trap - EXIT INT TERM
	case "$WORK_DIR" in
		"$TMP_PARENT"/duckyan_pgplan.*) rm -rf -- "$WORK_DIR" ;;
		*) printf 'experiment.sh: refusing to remove unexpected temporary path: %s\n' "$WORK_DIR" >&2 ;;
	esac
	exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

TIMEOUT_BIN=""
if [ "$TIMEOUT_SECS" -gt 0 ]; then
	TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
	[ -n "$TIMEOUT_BIN" ] || die "a timeout was requested, but neither timeout nor gtimeout is installed"
fi

# Snapshot before validation or execution. The shared standard-library
# normalizer both rejects extra statements and emits the exact bytes hashed by
# plan capture; native mode therefore cannot execute anything PGPlan did
# not validate.
cp -- "$QUERY_PATH" "$OUT_DIR/provenance/query.sql"
CANONICAL_QUERY="$WORK_DIR/query.canonical.sql"
if ! "$PYTHON_BIN" "$NORMALIZER" --emit-canonical-query \
	--query "$OUT_DIR/provenance/query.sql" > "$CANONICAL_QUERY"; then
	die "query validation failed: $QUERY_PATH"
fi
QUERY_SQL="$(<"$CANONICAL_QUERY")"
[ -n "$QUERY_SQL" ] || die "query file is empty: $QUERY_PATH"

sql_escape_literal() {
	printf '%s' "$1" | sed "s/'/''/g"
}

statement_timeout_sql() {
	[ "$TIMEOUT_SECS" -gt 0 ] || return 0
	printf 'SET max_execution_time=%s;\n' "$((TIMEOUT_SECS * 1000))"
}

config_sql() {
	case "$1" in
		native)
			printf "RESET VARIABLE pgplan;\nSET disabled_optimizers TO 'outer_yan';\n" ;;
		pgplan)
			printf "SET disabled_optimizers TO 'outer_yan';\nSET VARIABLE pgplan = '%s';\n" "$PLAN_SQL" ;;
		outer_yan)
			printf "RESET VARIABLE pgplan;\nSET disabled_optimizers TO '';\n" ;;
		*)
			die "internal error: unknown configuration '$1'" ;;
	esac
}

emit_bare_query() {
	# Put the terminator on its own line so a valid trailing `--` comment in
	# the query file cannot consume it.
	printf '%s\n;\n' "$QUERY_SQL"
}

# run_duck SQL STDOUT STDERR MULTIPLIER [OY_TRACE] [DATABASE]
# MULTIPLIER is N+1 for a warm-up plus N measured executions. SQL also carries
# the per-statement limit; this outer watchdog only prevents a wedged process.
run_duck() {
	local sql_file="$1" stdout_file="$2" stderr_file="$3" multiplier="$4"
	local oy_trace="${5:-}" database="${6:-$EXECUTION_DB}" watchdog=0
	local -a command
	command=("$DUCKDB_BIN" -no-init -bail "$database")
	if [ "$TIMEOUT_SECS" -gt 0 ]; then
		watchdog=$((TIMEOUT_SECS * multiplier + TIMEOUT_GRACE))
		command=("$TIMEOUT_BIN" "$watchdog" "${command[@]}")
	fi
	if [ -n "$oy_trace" ]; then
		DUCKDB_OYTRACE="$oy_trace" "${command[@]}" < "$sql_file" > "$stdout_file" 2> "$stderr_file"
	else
		"${command[@]}" < "$sql_file" > "$stdout_file" 2> "$stderr_file"
	fi
}

is_duck_timeout() {
	local rc="$1" stderr_file="$2"
	[ "$TIMEOUT_SECS" -gt 0 ] || return 1
	[ "$rc" -eq 124 ] && return 0
	# This fork reports a max_execution_time cancellation with this exact
	# diagnostic. Do not classify arbitrary errors that merely mention the
	# timeout setting as SKIP.
	grep -Fqx 'INTERRUPT Error: Interrupted!' "$stderr_file" 2>/dev/null
}

handle_duck_failure() {
	local rc="$1" stderr_file="$2" phase="$3" config="$4" diagnostic="$5"
	if is_duck_timeout "$rc" "$stderr_file"; then
		local message="[PGPLAN] TIMEOUT phase=$phase config=$config limit_seconds=$TIMEOUT_SECS"
		printf '%s\n' "$message" > "$OUT_DIR/checks/timeout.txt"
		printf 'finished_utc=%s\nstatus=SKIP\nskip_reason=execution_timeout\n' \
			"$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >> "$OUT_DIR/provenance/manifest.txt"
		printf '%s\n' "$message" >&2
		exit 124
	fi
	die "$diagnostic (exit=$rc; see $stderr_file)"
}

# Bound result framing, sorting, comparison, counting, and hashing just like a
# DuckDB statement. A fast engine query can still emit a very large multiset,
# so leaving these steps unbounded would make --timeout ineffective for the
# overall correctness phase.
run_postprocess() {
	local stdout_file="$1" stderr_file="$2"
	shift 2
	local -a command=("$@")
	if [ "$TIMEOUT_SECS" -gt 0 ]; then
		command=("$TIMEOUT_BIN" "$TIMEOUT_SECS" "${command[@]}")
	fi
	"${command[@]}" > "$stdout_file" 2> "$stderr_file"
}

handle_postprocess_failure() {
	local rc="$1" stderr_file="$2" phase="$3" config="$4" diagnostic="$5"
	if [ "$TIMEOUT_SECS" -gt 0 ] && [ "$rc" -eq 124 ]; then
		local message="[PGPLAN] TIMEOUT phase=$phase config=$config limit_seconds=$TIMEOUT_SECS"
		printf '%s\n' "$message" > "$OUT_DIR/checks/timeout.txt"
		printf 'finished_utc=%s\nstatus=SKIP\nskip_reason=postprocess_timeout\n' \
			"$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >> "$OUT_DIR/provenance/manifest.txt"
		printf '%s\n' "$message" >&2
		exit 124
	fi
	die "$diagnostic (exit=$rc; see $stderr_file)"
}

sha256_file() {
	local path="$1"
	local bounded="${2:-0}"
	local -a command
	local digest digest_field=1
	if command -v sha256sum >/dev/null 2>&1; then
		command=(sha256sum -- "$path")
	elif command -v shasum >/dev/null 2>&1; then
		command=(shasum -a 256 -- "$path")
	elif command -v openssl >/dev/null 2>&1; then
		command=(openssl dgst -sha256 "$path")
		digest_field=0
	else
		die "sha256sum, shasum, or openssl is required for provenance"
	fi
	if [ "$bounded" = "1" ] && [ "$TIMEOUT_SECS" -gt 0 ]; then
		command=("$TIMEOUT_BIN" "$TIMEOUT_SECS" "${command[@]}")
	fi
	if [ "$digest_field" -eq 1 ]; then
		digest="$("${command[@]}" | awk '{print $1}')" || return $?
	else
		digest="$("${command[@]}" | awk '{print $NF}')" || return $?
	fi
	case "$digest" in
		????????????????????????????????????????????????????????????????)
			case "$digest" in
				*[!0-9a-fA-F]*) printf 'invalid SHA-256 output for %s\n' "$path" >&2; return 1 ;;
			esac ;;
		*) printf 'invalid SHA-256 output for %s\n' "$path" >&2; return 1 ;;
	esac
	printf '%s\n' "$(printf '%s' "$digest" | tr 'A-F' 'a-f')"
}

assert_no_active_execution_wal() {
	local real_database wal_path previous=""
	real_database="$("$PYTHON_BIN" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$EXECUTION_DB")"
	for wal_path in "${EXECUTION_DB}.wal" "${real_database}.wal"; do
		[ "$wal_path" != "$previous" ] || continue
		previous="$wal_path"
		if [ -e "$wal_path" ] || [ -L "$wal_path" ]; then
			[ ! -L "$wal_path" ] || die "execution database WAL path is not a regular file: $wal_path"
			[ -f "$wal_path" ] || die "execution database WAL path is not a regular file: $wal_path"
			[ ! -s "$wal_path" ] || die "execution database has a nonempty WAL; checkpoint it before fingerprinting: $wal_path"
		fi
	done
}

cp -- "$PLAN_PATH" "$OUT_DIR/provenance/postgres_plan.json"
QUERY_SHA256="$(sha256_file "$OUT_DIR/provenance/query.sql")"
PLAN_SHA256="$(sha256_file "$OUT_DIR/provenance/postgres_plan.json")"
if [ -n "$DUCKDB_BIN_SHA256" ]; then
	DUCKDB_BIN_SHA256="$(printf '%s' "$DUCKDB_BIN_SHA256" | tr 'A-F' 'a-f')"
	DUCKDB_BIN_SHA256_SOURCE=provided
else
	DUCKDB_BIN_SHA256="$(sha256_file "$DUCKDB_BIN")"
	DUCKDB_BIN_SHA256_SOURCE=computed
fi
if [ -n "$EXECUTION_DB_SHA256" ]; then
	EXECUTION_DB_SHA256="$(printf '%s' "$EXECUTION_DB_SHA256" | tr 'A-F' 'a-f')"
	EXECUTION_DB_SHA256_SOURCE=provided
elif [ "$NEED_EXECUTION_DB_SHA256" -eq 1 ]; then
	assert_no_active_execution_wal
	EXECUTION_DB_SHA256="$(sha256_file "$EXECUTION_DB")"
	assert_no_active_execution_wal
	EXECUTION_DB_SHA256_SOURCE=computed
else
	assert_no_active_execution_wal
	EXECUTION_DB_SHA256=NOT_COLLECTED
	EXECUTION_DB_SHA256_SOURCE=not_collected
fi
if [ "$COMPARISON_MODE" = "none" ]; then
	CORRECTNESS_DB_SHA256=NOT_RUN
elif [ "$CORRECTNESS_DB" = "$EXECUTION_DB" ]; then
	CORRECTNESS_DB_SHA256="$EXECUTION_DB_SHA256"
else
	CORRECTNESS_DB_SHA256="$(sha256_file "$CORRECTNESS_DB")"
fi
for fingerprint in "$DUCKDB_BIN_SHA256"; do
	case "$fingerprint" in
		????????????????????????????????????????????????????????????????)
			case "$fingerprint" in *[!0-9a-f]*) die "computed SHA-256 fingerprint is invalid" ;; esac ;;
		*) die "computed SHA-256 fingerprint is invalid" ;;
	esac
done
if [ "$EXECUTION_DB_SHA256" != "NOT_COLLECTED" ]; then
	case "$EXECUTION_DB_SHA256" in
		????????????????????????????????????????????????????????????????)
			case "$EXECUTION_DB_SHA256" in *[!0-9a-f]*) die "computed SHA-256 fingerprint is invalid" ;; esac ;;
		*) die "computed SHA-256 fingerprint is invalid" ;;
	esac
fi
if [ "$CORRECTNESS_DB_SHA256" != "NOT_RUN" ] && \
		[ "$CORRECTNESS_DB_SHA256" != "NOT_COLLECTED" ]; then
	case "$CORRECTNESS_DB_SHA256" in
		????????????????????????????????????????????????????????????????)
			case "$CORRECTNESS_DB_SHA256" in *[!0-9a-f]*) die "computed SHA-256 fingerprint is invalid" ;; esac ;;
		*) die "computed SHA-256 fingerprint is invalid" ;;
	esac
fi
PLAN_METADATA="$({
	"$PYTHON_BIN" -c \
		'import json,sys; p=json.load(open(sys.argv[1], encoding="utf-8"))["postgres"]; print(p["plan_data"]); print(p.get("plan_schema", "public"))' \
		"$OUT_DIR/provenance/postgres_plan.json"
})" || die "could not read postgres.plan_data/plan_schema from artifact"
PLAN_DATA="$(printf '%s\n' "$PLAN_METADATA" | sed -n '1p')"
PLAN_SCHEMA="$(printf '%s\n' "$PLAN_METADATA" | sed -n '2p')"
[ -n "$PLAN_DATA" ] && [ -n "$PLAN_SCHEMA" ] || die "artifact plan provenance is empty"
# All PGPlan processes consume the immutable provenance copy. This prevents an
# independently regenerated source artifact from changing half-way through a
# benchmark run.
PGPLAN_PLAN_PATH="$OUT_DIR/provenance/postgres_plan.json"
PLAN_SQL="$(sql_escape_literal "$PGPLAN_PLAN_PATH")"
# DuckDB CSV otherwise renders SQL NULL exactly like an empty VARCHAR. Use one
# nonce for all three runs and record it; a collision with real query text is
# vanishingly unlikely and can be audited from the raw CSV.
NULL_SENTINEL="__DUCKYAN_SQL_NULL_${$}_${RANDOM}_${RANDOM}__"
STARTED_UTC="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
{
	if [ -n "$REUSE_CORRECTNESS_FROM" ]; then
		printf 'description=%s\n' "PostgreSQL 16.2's $PLAN_DATA-selected logical join tree: performance-only run using a validated prior target-scale correctness receipt; DuckDB EXPLAIN, semantic verification, and timing on the target database."
		printf 'correctness_request=reuse\n'
	elif [ "$COMPARISON_MODE" = "both" ]; then
		printf 'description=%s\n' "PostgreSQL 16.2's $PLAN_DATA-selected logical join tree: exact Original-versus-PGPlan and Original-versus-OuterYan equality on the correctness database; DuckDB EXPLAIN, semantic verification, and timing on the target database."
		printf 'correctness_request=fresh\n'
	elif [ "$COMPARISON_MODE" = "pgplan-only" ]; then
		printf 'description=%s\n' "PostgreSQL 16.2's $PLAN_DATA-selected logical join tree: Original-versus-PGPlan correctness comparison only; DuckDB EXPLAIN, semantic verification, and Original/PGPlan/OuterYan timing on the target database."
		printf 'correctness_request=partial\n'
	else
		printf 'description=%s\n' "PostgreSQL 16.2's $PLAN_DATA-selected logical join tree: correctness not run; DuckDB EXPLAIN, semantic verification, and Original/PGPlan/OuterYan timing on the target database."
		printf 'correctness_request=none\n'
	fi
	printf 'comparison_mode=%s\n' "$COMPARISON_MODE"
	printf 'started_utc=%s\n' "$STARTED_UTC"
	printf 'duckdb_bin=%s\nexecution_db=%s\ncorrectness_db=%s\nquery=%s\nplan_source=%s\npgplan=%s\n' \
		"$DUCKDB_BIN" "$EXECUTION_DB" "$CORRECTNESS_DB" "$QUERY_PATH" "$PLAN_PATH" "$PGPLAN_PLAN_PATH"
	printf 'query_sha256=%s\nplan_sha256=%s\nruns=%s\nthreads=%s\n' \
		"$QUERY_SHA256" "$PLAN_SHA256" "$RUNS" "$THREADS"
	printf 'duckdb_bin_sha256=%s\nduckdb_bin_sha256_source=%s\n' \
		"$DUCKDB_BIN_SHA256" "$DUCKDB_BIN_SHA256_SOURCE"
	printf 'execution_db_sha256=%s\nexecution_db_sha256_source=%s\ncorrectness_db_sha256=%s\n' \
		"$EXECUTION_DB_SHA256" "$EXECUTION_DB_SHA256_SOURCE" "$CORRECTNESS_DB_SHA256"
	printf 'postgres_plan_data=%s\npostgres_plan_schema=%s\n' "$PLAN_DATA" "$PLAN_SCHEMA"
	printf 'csv_null_sentinel=%s\n' "$NULL_SENTINEL"
	printf 'timeout_seconds=%s\nhost=%s\nkernel=%s\n' \
		"$TIMEOUT_SECS" "$(hostname 2>/dev/null || printf unknown)" "$(uname -sr 2>/dev/null || printf unknown)"
} > "$OUT_DIR/provenance/manifest.txt"

VERSION_SQL="$WORK_DIR/version.sql"
{
	printf '.headers on\n.mode csv\n'
	printf 'SELECT * FROM pragma_version();\n'
} > "$VERSION_SQL"
if run_duck "$VERSION_SQL" "$OUT_DIR/settings/version.csv" \
		"$OUT_DIR/settings/version.stderr" 1; then
	:
else
	rc=$?
	handle_duck_failure "$rc" "$OUT_DIR/settings/version.stderr" version metadata \
		"failed to capture DuckDB version"
fi
DUCKDB_VERSION_SHA256="$(sha256_file "$OUT_DIR/settings/version.csv")"
printf 'duckdb_version_sha256=%s\n' "$DUCKDB_VERSION_SHA256" \
	>> "$OUT_DIR/provenance/manifest.txt"

printf 'Capturing settings and EXPLAIN plans...\n'
for config in native pgplan outer_yan; do
	SETTINGS_SQL="$WORK_DIR/settings_${config}.sql"
	{
		printf '.headers on\n.mode csv\n'
		printf 'PRAGMA threads=%s;\n' "$THREADS"
		statement_timeout_sql
		# Do not activate PGPlan before metadata SELECTs: the importer is deliberately
		# fail-closed for every SELECT in the session, including introspection.
		if [ "$config" = pgplan ]; then
			printf "SET disabled_optimizers TO 'outer_yan';\n"
		else
			config_sql "$config"
		fi
		printf "SELECT name, value FROM duckdb_settings() WHERE name IN ('threads', 'disabled_optimizers', 'max_execution_time') ORDER BY name;\n"
		if [ "$config" = pgplan ]; then
			printf "SELECT 'pgplan' AS name, '%s' AS value, 'VARCHAR' AS type;\n" "$PLAN_SQL"
		else
			printf "SELECT name, value, type FROM duckdb_variables() WHERE name = 'pgplan';\n"
		fi
	} > "$SETTINGS_SQL"
	if run_duck "$SETTINGS_SQL" "$OUT_DIR/settings/${config}.csv" \
			"$OUT_DIR/settings/${config}.stderr" 1; then
		:
	else
		rc=$?
		handle_duck_failure "$rc" "$OUT_DIR/settings/${config}.stderr" \
			settings "$config" "failed to capture $config settings"
	fi

	EXPLAIN_SQL="$WORK_DIR/explain_${config}.sql"
	{
		printf "PRAGMA threads=%s;\nPRAGMA explain_output='all';\n" "$THREADS"
		statement_timeout_sql
		config_sql "$config"
		printf 'EXPLAIN '
		emit_bare_query
	} > "$EXPLAIN_SQL"
	OY_TRACE=""
	[ "$config" != outer_yan ] || OY_TRACE="$OUT_DIR/traces/outer_yan_explain.trace"
	if run_duck "$EXPLAIN_SQL" "$OUT_DIR/plans/${config}.txt" \
			"$OUT_DIR/plans/${config}.stderr" 1 "$OY_TRACE"; then
		:
	else
		rc=$?
		handle_duck_failure "$rc" "$OUT_DIR/plans/${config}.stderr" \
			explain "$config" "failed to capture $config EXPLAIN"
	fi
done

if ! tr -d '\r' < "$OUT_DIR/settings/native.csv" | grep -qx 'disabled_optimizers,outer_yan' ||
	! tr -d '\r' < "$OUT_DIR/settings/pgplan.csv" | grep -qx 'disabled_optimizers,outer_yan' ||
	! tr -d '\r' < "$OUT_DIR/settings/outer_yan.csv" | grep -qx 'disabled_optimizers,'; then
	die "captured optimizer settings do not match native/PGPlan/OuterYan mode isolation"
fi
printf '%s\n' \
	'PASS: native and PGPlan disable OuterYan; only the OuterYan mode enables it' \
	> "$OUT_DIR/checks/configuration_isolation.txt"

if grep -Eq 'SJ_(BUILD|PROBE)' "$OUT_DIR/plans/pgplan.txt"; then
	printf 'FAIL: PGPlan EXPLAIN contains OuterYan semi-join operators\n' > "$OUT_DIR/checks/pgplan_no_semijoin.txt"
	die "PGPlan EXPLAIN contains SJ_BUILD or SJ_PROBE"
fi
printf 'PASS: PGPlan EXPLAIN contains no SJ_BUILD or SJ_PROBE\n' > "$OUT_DIR/checks/pgplan_no_semijoin.txt"

# The PGPlan importer emits one JSON machine record per optimization.
# Keep the raw stderr as well as a convenient trace-only extract.
grep '^\[PGPLAN\]' "$OUT_DIR/plans/pgplan.stderr" > "$OUT_DIR/traces/pgplan_explain.trace" || true
if [ ! -s "$OUT_DIR/traces/pgplan_explain.trace" ]; then
	die "PGPlan EXPLAIN emitted no [PGPLAN] diagnostic (see $OUT_DIR/plans/pgplan.stderr)"
fi
grep '^\[OY_DECISION\]' "$OUT_DIR/traces/outer_yan_explain.trace" \
	> "$OUT_DIR/traces/outer_yan_decision.trace" || true
if [ ! -s "$OUT_DIR/traces/outer_yan_decision.trace" ]; then
	die "OuterYan EXPLAIN emitted no [OY_DECISION] record (see $OUT_DIR/traces/outer_yan_explain.trace)"
fi
OY_SELECTED_PLAN="$(sed -n 's/.* selected_plan=\([^ ]*\).*/\1/p' \
	"$OUT_DIR/traces/outer_yan_decision.trace" | sed -n '1p')"
case "$OY_SELECTED_PLAN" in
	DUCKDB|OUTERYAN) ;;
	*) die "could not parse OuterYan selected_plan from [OY_DECISION]" ;;
esac
printf 'PASS: OuterYan mode selected_plan=%s\n' "$OY_SELECTED_PLAN" \
	> "$OUT_DIR/checks/outer_yan_selection.txt"
printf 'outer_yan_selected_plan=%s\n' "$OY_SELECTED_PLAN" \
	>> "$OUT_DIR/provenance/manifest.txt"
printf 'OuterYan decision: selected_plan=%s\n' "$OY_SELECTED_PLAN"

create_correctness_receipt() {
	local receipt="$OUT_DIR/correctness/receipt.txt"
	local fields="$WORK_DIR/correctness_receipt_fields.tsv"
	if ! "$PYTHON_BIN" -c '
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
query_sha, plan_sha, binary_sha, database_sha, version_sha = sys.argv[2:7]
execution_db, correctness_db, created_utc, fields_path = sys.argv[7:11]
correctness_db_sha, correctness_threads, timeout_seconds = sys.argv[11:14]

def digest(path):
    value = hashlib.sha256(path.read_bytes()).hexdigest()
    return value

def pgplan_fields(path):
    events = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("[PGPLAN]"):
            continue
        record = json.loads(line[len("[PGPLAN]"):].strip())
        event = record.get("event")
        if event in ("imported", "verified"):
            if event in events:
                raise ValueError("duplicate PGPlan {} event".format(event))
            events[event] = record
    if set(events) != {"imported", "verified"}:
        raise ValueError("PGPlan trace must contain exactly imported and verified events")
    imported, verified = events["imported"], events["verified"]
    artifact = imported.get("artifact_raw_signature")
    imported_raw = imported.get("imported_raw_signature")
    expected = imported.get("expected_semantic_signature")
    verified_expected = verified.get("expected_semantic_signature")
    final = verified.get("final_semantic_signature")
    values = (artifact, imported_raw, expected, verified_expected, final)
    if not all(isinstance(value, str) and value and "\n" not in value for value in values):
        raise ValueError("PGPlan trace signatures are missing or malformed")
    if artifact != imported_raw:
        raise ValueError("PGPlan imported raw signature differs from artifact")
    if expected != verified_expected or expected != final:
        raise ValueError("PGPlan final semantic signature differs from expected")
    if imported.get("query_sha256_verified") is not True:
        raise ValueError("PGPlan trace did not verify the query SHA-256")
    implied = imported.get("implied_equality_count", 0)
    if isinstance(implied, bool) or not isinstance(implied, int) or implied < 0:
        raise ValueError("PGPlan implied equality count is invalid")
    return artifact, imported_raw, expected, final, str(implied)

def oy_selected(path):
    records = [line for line in path.read_text(encoding="utf-8").splitlines()
               if line.startswith("[OY_DECISION]")]
    if len(records) != 1:
        raise ValueError("OuterYan trace must contain exactly one decision record")
    matches = re.findall(r"(?:^| )selected_plan=(DUCKDB|OUTERYAN)(?: |$)", records[0])
    if len(matches) != 1:
        raise ValueError("OuterYan decision has no unique selected_plan")
    return matches[0]

correctness = root / "correctness"
traces = root / "traces"
context = correctness / "sealed_context"
context.mkdir()
context_sources = [
    ("settings_native", root / "settings" / "native.csv"),
    ("settings_pgplan", root / "settings" / "pgplan.csv"),
    ("settings_outer_yan", root / "settings" / "outer_yan.csv"),
    ("plan_native", root / "plans" / "native.txt"),
    ("plan_pgplan", root / "plans" / "pgplan.txt"),
    ("plan_outer_yan", root / "plans" / "outer_yan.txt"),
    ("outer_yan_decision", traces / "outer_yan_decision.trace"),
]
plan_path = str(root / "provenance" / "postgres_plan.json").encode("utf-8")
for name, path in context_sources:
    data = path.read_bytes().replace(plan_path, b"<PGPLAN_ARTIFACT>")
    (context / (name + ".snapshot")).write_bytes(data)
with (correctness / "row_counts.tsv").open(newline="", encoding="utf-8") as source:
    rows = list(csv.DictReader(source, delimiter="\t"))
if [row.get("configuration") for row in rows] != ["native", "pgplan", "outer_yan"]:
    raise ValueError("row_counts.tsv must contain native, pgplan, outer_yan in order")
counts = {row.get("rows") for row in rows}
if len(counts) != 1 or not next(iter(counts), "").isdigit():
    raise ValueError("complete-comparison row counts are not equal non-negative integers")
row_count = next(iter(counts))
with (correctness / "multiset_sha256.tsv").open(newline="", encoding="utf-8") as source:
    hashes = list(csv.DictReader(source, delimiter="\t"))
if len(hashes) != 1 or hashes[0].get("rows") != row_count:
    raise ValueError("multiset hash row count differs from complete-comparison row count")
multiset_sha = hashes[0].get("sha256", "").lower()
if re.fullmatch(r"[0-9a-f]{64}", multiset_sha) is None:
    raise ValueError("multiset SHA-256 is invalid")
if (correctness / "status.txt").read_text(encoding="utf-8") != \
        "PASS: native, PGPlan, and OuterYan complete multisets are identical\n":
    raise ValueError("correctness status is not the exact complete-comparison PASS marker")
for config in ("pgplan", "outer_yan"):
    expected = "PASS native == {}\n".format(config)
    if (correctness / (config + ".comparison.txt")).read_text(encoding="utf-8") != expected:
        raise ValueError("{} comparison is not PASS".format(config))
pg_trace = traces / "pgplan_correctness.trace"
oy_trace = traces / "outer_yan_correctness_decision.trace"
artifact, imported_raw, expected, final, implied = pgplan_fields(pg_trace)
selected = oy_selected(oy_trace)
evidence = [
    ("row_counts", correctness / "row_counts.tsv"),
    ("multiset_table", correctness / "multiset_sha256.tsv"),
    ("status", correctness / "status.txt"),
    ("pgplan_comparison", correctness / "pgplan.comparison.txt"),
    ("outer_yan_comparison", correctness / "outer_yan.comparison.txt"),
    ("pgplan_trace", pg_trace),
    ("outer_yan_trace", oy_trace),
]
evidence.extend(
    ("context_" + name, context / (name + ".snapshot"))
    for name, unused_path in context_sources
)
scope = "target" if execution_db == correctness_db else "bounded"
receipt = [
    ("format", "duckyan.pgplan_correctness_receipt.v1"),
    ("status", "PASS"),
    ("scope", scope),
    ("comparison_mode", "both"),
    ("created_utc", created_utc),
    ("execution_db", execution_db),
    ("correctness_db", correctness_db),
    ("query_sha256", query_sha),
    ("plan_sha256", plan_sha),
    ("duckdb_bin_sha256", binary_sha),
    ("execution_db_sha256", database_sha),
    ("correctness_db_sha256", correctness_db_sha),
    ("duckdb_version_sha256", version_sha),
    ("correctness_threads", correctness_threads),
    ("timeout_seconds", timeout_seconds),
    ("rows", row_count),
    ("multiset_sha256", multiset_sha),
    ("pgplan_artifact_raw_signature", artifact),
    ("pgplan_imported_raw_signature", imported_raw),
    ("pgplan_expected_semantic_signature", expected),
    ("pgplan_final_semantic_signature", final),
    ("pgplan_implied_equality_count", implied),
    ("outer_yan_selected_plan", selected),
]
receipt.extend((name + "_sha256", digest(path)) for name, path in evidence)
for key, value in receipt:
    if "\n" in value or "\r" in value:
        raise ValueError("receipt value contains a newline: {}".format(key))
Path(fields_path).write_text(
    "".join("{}={}\n".format(key, value) for key, value in receipt),
    encoding="utf-8",
)
print("{}\t{}\t{}".format(row_count, multiset_sha, selected))
' "$OUT_DIR" "$QUERY_SHA256" "$PLAN_SHA256" "$DUCKDB_BIN_SHA256" \
		"$EXECUTION_DB_SHA256" "$DUCKDB_VERSION_SHA256" "$EXECUTION_DB" \
		"$CORRECTNESS_DB" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$fields" \
		"$CORRECTNESS_DB_SHA256" "$THREADS" "$TIMEOUT_SECS" \
		> "$WORK_DIR/correctness_receipt_result.tsv"; then
		die "could not seal fresh correctness evidence"
	fi
	cp -- "$fields" "$receipt"
	CORRECTNESS_RECEIPT_SHA256="$(sha256_file "$receipt")"
	IFS=$'\t' read -r CORRECTNESS_ROWS CORRECTNESS_MULTISET_SHA256 \
		CORRECTNESS_OY_SELECTED_PLAN < "$WORK_DIR/correctness_receipt_result.tsv"
	{
		printf 'correctness_origin=FRESH\ncorrectness_status=PASS\ncorrectness_comparison_executed=1\ncorrectness_comparison_set=both\n'
		printf 'correctness_scope=%s\ncorrectness_threads=%s\ncorrectness_rows=%s\ncorrectness_multiset_sha256=%s\n' \
			"$([ "$CORRECTNESS_DB" = "$EXECUTION_DB" ] && printf target || printf bounded)" \
			"$THREADS" "$CORRECTNESS_ROWS" "$CORRECTNESS_MULTISET_SHA256"
		printf 'correctness_receipt_sha256=%s\n' "$CORRECTNESS_RECEIPT_SHA256"
	} >> "$OUT_DIR/provenance/manifest.txt"
}

reuse_correctness() {
	local source="$REUSE_CORRECTNESS_FROM" validation="$WORK_DIR/reuse_validation.tsv"
	if ! "$PYTHON_BIN" -c '
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

source = Path(sys.argv[1])
current = {
    "query_sha256": sys.argv[2], "plan_sha256": sys.argv[3],
    "duckdb_bin_sha256": sys.argv[4], "execution_db_sha256": sys.argv[5],
    "duckdb_version_sha256": sys.argv[6], "execution_db": sys.argv[7],
    "correctness_threads": sys.argv[8],
    "timeout_seconds": sys.argv[9],
}
current_trace = Path(sys.argv[10])
current_oy_trace = Path(sys.argv[11])
current_root = Path(sys.argv[12])

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def key_values(path):
    values = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        key, separator, value = line.partition("=")
        if not separator or not key or key in values:
            raise ValueError("{}:{}: malformed or duplicate key".format(path, number))
        values[key] = value
    return values

def pgplan_fields(path):
    events = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("[PGPLAN]"):
            continue
        record = json.loads(line[len("[PGPLAN]"):].strip())
        event = record.get("event")
        if event in ("imported", "verified"):
            if event in events:
                raise ValueError("duplicate PGPlan {} event".format(event))
            events[event] = record
    if set(events) != {"imported", "verified"}:
        raise ValueError("PGPlan trace must contain exactly imported and verified events")
    imported, verified = events["imported"], events["verified"]
    fields = {
        "pgplan_artifact_raw_signature": imported.get("artifact_raw_signature"),
        "pgplan_imported_raw_signature": imported.get("imported_raw_signature"),
        "pgplan_expected_semantic_signature": imported.get("expected_semantic_signature"),
        "pgplan_final_semantic_signature": verified.get("final_semantic_signature"),
        "pgplan_implied_equality_count": str(imported.get("implied_equality_count", 0)),
    }
    if not all(isinstance(value, str) and value for value in fields.values()):
        raise ValueError("PGPlan trace fields are missing")
    if fields["pgplan_artifact_raw_signature"] != fields["pgplan_imported_raw_signature"]:
        raise ValueError("PGPlan raw signatures differ")
    if fields["pgplan_expected_semantic_signature"] != \
            verified.get("expected_semantic_signature") or \
            fields["pgplan_expected_semantic_signature"] != fields["pgplan_final_semantic_signature"]:
        raise ValueError("PGPlan semantic signatures differ")
    if imported.get("query_sha256_verified") is not True:
        raise ValueError("PGPlan query SHA-256 was not verified")
    return fields

def oy_selected(path):
    records = [line for line in path.read_text(encoding="utf-8").splitlines()
               if line.startswith("[OY_DECISION]")]
    if len(records) != 1:
        raise ValueError("OuterYan trace must contain exactly one decision")
    matches = re.findall(r"(?:^| )selected_plan=(DUCKDB|OUTERYAN)(?: |$)", records[0])
    if len(matches) != 1:
        raise ValueError("OuterYan selected plan is missing or ambiguous")
    return matches[0]

manifest_path = source / "provenance" / "manifest.txt"
manifest = key_values(manifest_path)
receipt_path = source / "correctness" / "receipt.txt"
receipt = key_values(receipt_path)
receipt_sha = digest(receipt_path)
if manifest.get("correctness_origin") != "FRESH" or manifest.get("correctness_status") != "PASS":
    raise ValueError("reuse source is not fresh PASS correctness evidence")
if manifest.get("correctness_receipt_sha256") != receipt_sha:
    raise ValueError("source manifest does not seal the correctness receipt")
if receipt.get("format") != "duckyan.pgplan_correctness_receipt.v1" or \
        receipt.get("status") != "PASS" or receipt.get("scope") != "target":
    raise ValueError("correctness receipt is not a target-scale PASS receipt")
if receipt.get("comparison_mode", "both") != "both":
    raise ValueError("correctness receipt is not a complete both-mode comparison")
for key, value in current.items():
    if receipt.get(key) != value or manifest.get(key) != value:
        raise ValueError("current {} does not match reuse evidence".format(key))
if receipt.get("correctness_db") != current["execution_db"] or \
        manifest.get("correctness_db") != current["execution_db"]:
    raise ValueError("reuse evidence was not checked on the current target database")
if receipt.get("correctness_db_sha256") != current["execution_db_sha256"] or \
        manifest.get("correctness_db_sha256") != current["execution_db_sha256"]:
    raise ValueError("reuse correctness database hash differs from target database hash")
if digest(source / "provenance" / "query.sql") != current["query_sha256"] or \
        digest(source / "provenance" / "postgres_plan.json") != current["plan_sha256"] or \
        digest(source / "settings" / "version.csv") != current["duckdb_version_sha256"]:
    raise ValueError("reuse provenance files do not match their sealed hashes")
correctness = source / "correctness"
traces = source / "traces"
evidence = {
    "row_counts": correctness / "row_counts.tsv",
    "multiset_table": correctness / "multiset_sha256.tsv",
    "status": correctness / "status.txt",
    "pgplan_comparison": correctness / "pgplan.comparison.txt",
    "outer_yan_comparison": correctness / "outer_yan.comparison.txt",
    "pgplan_trace": traces / "pgplan_correctness.trace",
    "outer_yan_trace": traces / "outer_yan_correctness_decision.trace",
}
context = correctness / "sealed_context"
context_names = (
    "settings_native", "settings_pgplan", "settings_outer_yan",
    "plan_native", "plan_pgplan", "plan_outer_yan", "outer_yan_decision",
)
for name in context_names:
    evidence["context_" + name] = context / (name + ".snapshot")
for name, path in evidence.items():
    if receipt.get(name + "_sha256") != digest(path):
        raise ValueError("sealed evidence hash differs for {}".format(name))
with evidence["row_counts"].open(newline="", encoding="utf-8") as stream:
    row_table = list(csv.DictReader(stream, delimiter="\t"))
if [row.get("configuration") for row in row_table] != ["native", "pgplan", "outer_yan"]:
    raise ValueError("reuse row counts have invalid configurations")
counts = {row.get("rows") for row in row_table}
if len(counts) != 1 or not next(iter(counts), "").isdigit() or next(iter(counts)) != receipt.get("rows"):
    raise ValueError("reuse row counts are invalid or differ from receipt")
with evidence["multiset_table"].open(newline="", encoding="utf-8") as stream:
    hashes = list(csv.DictReader(stream, delimiter="\t"))
if len(hashes) != 1 or hashes[0].get("sha256", "").lower() != receipt.get("multiset_sha256") \
        or hashes[0].get("rows") != receipt.get("rows"):
    raise ValueError("reuse multiset table differs from receipt")
if evidence["status"].read_text(encoding="utf-8") != \
        "PASS: native, PGPlan, and OuterYan complete multisets are identical\n":
    raise ValueError("reuse correctness status is not PASS")
for config in ("pgplan", "outer_yan"):
    if evidence[config + "_comparison"].read_text(encoding="utf-8") != \
            "PASS native == {}\n".format(config):
        raise ValueError("reuse {} comparison is not PASS".format(config))
source_context = {
    "settings_native": source / "settings" / "native.csv",
    "settings_pgplan": source / "settings" / "pgplan.csv",
    "settings_outer_yan": source / "settings" / "outer_yan.csv",
    "plan_native": source / "plans" / "native.txt",
    "plan_pgplan": source / "plans" / "pgplan.txt",
    "plan_outer_yan": source / "plans" / "outer_yan.txt",
    "outer_yan_decision": source / "traces" / "outer_yan_decision.trace",
}
current_context = {
    "settings_native": current_root / "settings" / "native.csv",
    "settings_pgplan": current_root / "settings" / "pgplan.csv",
    "settings_outer_yan": current_root / "settings" / "outer_yan.csv",
    "plan_native": current_root / "plans" / "native.txt",
    "plan_pgplan": current_root / "plans" / "pgplan.txt",
    "plan_outer_yan": current_root / "plans" / "outer_yan.txt",
    "outer_yan_decision": current_oy_trace,
}
source_plan_path = str(source / "provenance" / "postgres_plan.json").encode("utf-8")
current_plan_path = str(current_root / "provenance" / "postgres_plan.json").encode("utf-8")
for name, path in current_context.items():
    normalized = path.read_bytes().replace(current_plan_path, b"<PGPLAN_ARTIFACT>")
    sealed = evidence["context_" + name].read_bytes()
    source_normalized = source_context[name].read_bytes().replace(
        source_plan_path, b"<PGPLAN_ARTIFACT>"
    )
    if source_normalized != sealed or normalized != sealed or \
            hashlib.sha256(normalized).hexdigest() != \
            receipt.get("context_" + name + "_sha256"):
        raise ValueError("current settings/plan context differs for {}".format(name))
source_pg = pgplan_fields(evidence["pgplan_trace"])
target_pg = pgplan_fields(current_trace)
for key, value in source_pg.items():
    if receipt.get(key) != value or target_pg.get(key) != value:
        raise ValueError("PGPlan receipt/source/current trace mismatch for {}".format(key))
selected = oy_selected(evidence["outer_yan_trace"])
current_oy = oy_selected(current_oy_trace)
if receipt.get("outer_yan_selected_plan") != selected or selected != current_oy:
    raise ValueError("OuterYan receipt/source/current selected plan mismatch")
print("{}\t{}\t{}\t{}".format(receipt["rows"], receipt["multiset_sha256"], selected, receipt_sha))
' "$source" "$QUERY_SHA256" "$PLAN_SHA256" "$DUCKDB_BIN_SHA256" \
		"$EXECUTION_DB_SHA256" "$DUCKDB_VERSION_SHA256" "$EXECUTION_DB" \
		"$THREADS" "$TIMEOUT_SECS" "$OUT_DIR/traces/pgplan_explain.trace" \
		"$OUT_DIR/traces/outer_yan_decision.trace" "$OUT_DIR" > "$validation"; then
		die "correctness reuse evidence validation failed: $source"
	fi
	IFS=$'\t' read -r CORRECTNESS_ROWS CORRECTNESS_MULTISET_SHA256 \
		CORRECTNESS_OY_SELECTED_PLAN CORRECTNESS_RECEIPT_SHA256 < "$validation"
	cp -- "$source/correctness/receipt.txt" "$OUT_DIR/correctness/receipt.txt"
	for name in row_counts.tsv multiset_sha256.tsv status.txt \
		pgplan.comparison.txt outer_yan.comparison.txt; do
		cp -- "$source/correctness/$name" "$OUT_DIR/correctness/$name"
	done
	cp -- "$source/traces/pgplan_correctness.trace" \
		"$OUT_DIR/traces/pgplan_correctness.trace"
	cp -- "$source/traces/outer_yan_correctness_decision.trace" \
		"$OUT_DIR/traces/outer_yan_correctness_decision.trace"
	mkdir -p -- "$OUT_DIR/correctness/sealed_context"
	for name in settings_native settings_pgplan settings_outer_yan \
		plan_native plan_pgplan plan_outer_yan outer_yan_decision; do
		cp -- "$source/correctness/sealed_context/${name}.snapshot" \
			"$OUT_DIR/correctness/sealed_context/${name}.snapshot"
	done
	SOURCE_MANIFEST_SHA256="$(sha256_file "$source/provenance/manifest.txt")"
	{
		printf 'Fresh correctness was not executed in this run.\n'
		printf 'source=%s\nsource_receipt_sha256=%s\n' \
			"$source" "$CORRECTNESS_RECEIPT_SHA256"
	} > "$OUT_DIR/correctness/reuse.txt"
	{
		printf 'correctness_origin=REUSED\ncorrectness_status=PASS\ncorrectness_comparison_executed=0\ncorrectness_comparison_set=none\ncorrectness_scope=target\n'
		printf 'correctness_threads=%s\ncorrectness_rows=%s\ncorrectness_multiset_sha256=%s\n' \
			"$THREADS" "$CORRECTNESS_ROWS" "$CORRECTNESS_MULTISET_SHA256"
		printf 'correctness_outer_yan_selected_plan=%s\n' "$CORRECTNESS_OY_SELECTED_PLAN"
		printf 'correctness_receipt_sha256=%s\ncorrectness_reuse_source=%s\n' \
			"$CORRECTNESS_RECEIPT_SHA256" "$source"
		printf 'correctness_reuse_source_receipt_sha256=%s\n' \
			"$CORRECTNESS_RECEIPT_SHA256"
		printf 'correctness_reuse_source_manifest_sha256=%s\n' "$SOURCE_MANIFEST_SHA256"
	} >> "$OUT_DIR/provenance/manifest.txt"
	printf 'Reusing sealed target correctness from %s (no correctness query executed now).\n' "$source"
}

if [ -n "$REUSE_CORRECTNESS_FROM" ]; then
	reuse_correctness
elif [ "$COMPARISON_MODE" = "none" ]; then
	printf 'NOT_RUN: correctness queries and multiset comparisons were disabled by comparison_mode=none\n' \
		> "$OUT_DIR/correctness/status.txt"
	{
		printf 'correctness_origin=NOT_RUN\ncorrectness_status=NOT_RUN\n'
		printf 'correctness_comparison_executed=0\ncorrectness_comparison_set=none\n'
	} >> "$OUT_DIR/provenance/manifest.txt"
	printf 'Correctness comparison: NOT_RUN (comparison_mode=none).\n'
else
	printf 'Checking complete result multisets (bare query, external CSV sort)...\n'
	printf 'configuration\trows\n' > "$OUT_DIR/correctness/row_counts.tsv"
	CORRECTNESS_CONFIGS="native pgplan"
	[ "$COMPARISON_MODE" != "both" ] || CORRECTNESS_CONFIGS="$CORRECTNESS_CONFIGS outer_yan"
for config in $CORRECTNESS_CONFIGS; do
	RESULT_SQL="$WORK_DIR/result_${config}.sql"
	{
		printf '.headers off\n.mode csv\n.nullvalue %s\nPRAGMA threads=%s;\n' "$NULL_SENTINEL" "$THREADS"
		statement_timeout_sql
		config_sql "$config"
		emit_bare_query
	} > "$RESULT_SQL"
	OY_TRACE=""
	[ "$config" != outer_yan ] || OY_TRACE="$OUT_DIR/traces/outer_yan_correctness.trace"
	if run_duck "$RESULT_SQL" "$OUT_DIR/correctness/${config}.csv" \
			"$OUT_DIR/correctness/${config}.stderr" 1 "$OY_TRACE" \
			"$CORRECTNESS_DB"; then
		:
	else
		rc=$?
		handle_duck_failure "$rc" "$OUT_DIR/correctness/${config}.stderr" \
			correctness "$config" "$config correctness query failed"
	fi
	if run_postprocess "$OUT_DIR/correctness/${config}.records.jsonl" \
			"$OUT_DIR/correctness/${config}.frame.stderr" \
			"$PYTHON_BIN" "$CSV_RECORDS" "$OUT_DIR/correctness/${config}.csv"; then
		:
	else
		rc=$?
		handle_postprocess_failure "$rc" \
			"$OUT_DIR/correctness/${config}.frame.stderr" \
			correctness_frame "$config" "CSV record framing failed for $config results"
	fi
	if LC_ALL=C run_postprocess \
			"$OUT_DIR/correctness/${config}.sorted.records.jsonl" \
			"$OUT_DIR/correctness/${config}.sort.stderr" \
			sort "$OUT_DIR/correctness/${config}.records.jsonl"; then
		:
	else
		rc=$?
		handle_postprocess_failure "$rc" \
			"$OUT_DIR/correctness/${config}.sort.stderr" \
			correctness_sort "$config" "external sort failed for $config results"
	fi
	if run_postprocess "$OUT_DIR/correctness/${config}.row_count" \
			"$OUT_DIR/correctness/${config}.count.stderr" \
			wc -l "$OUT_DIR/correctness/${config}.records.jsonl"; then
		:
	else
		rc=$?
		handle_postprocess_failure "$rc" \
			"$OUT_DIR/correctness/${config}.count.stderr" \
			correctness_count "$config" "row counting failed for $config results"
	fi
	ROWS="$(awk '{print $1}' "$OUT_DIR/correctness/${config}.row_count")"
	case "$ROWS" in ''|*[!0-9]*) die "invalid row count for $config results: $ROWS" ;; esac
	printf '%s\t%s\n' "$config" "$ROWS" >> "$OUT_DIR/correctness/row_counts.tsv"
done

# Executing the correctness query must itself apply and verify the immutable
# artifact on the selected correctness database. Target EXPLAIN verification
# above does not substitute for this independent catalog/binding check.
grep '^\[PGPLAN\]' "$OUT_DIR/correctness/pgplan.stderr" \
	> "$OUT_DIR/traces/pgplan_correctness.trace" || true
if [ ! -s "$OUT_DIR/traces/pgplan_correctness.trace" ]; then
	die "PGPlan correctness execution emitted no [PGPLAN] diagnostic (see $OUT_DIR/correctness/pgplan.stderr)"
fi
if [ "$COMPARISON_MODE" = "both" ]; then
	grep '^\[OY_DECISION\]' "$OUT_DIR/traces/outer_yan_correctness.trace" \
		> "$OUT_DIR/traces/outer_yan_correctness_decision.trace" || true
	if [ ! -s "$OUT_DIR/traces/outer_yan_correctness_decision.trace" ]; then
		die "OuterYan correctness execution emitted no [OY_DECISION] record"
	fi
	CORRECTNESS_OY_SELECTED_PLAN="$(sed -n 's/.* selected_plan=\([^ ]*\).*/\1/p' \
		"$OUT_DIR/traces/outer_yan_correctness_decision.trace" | sed -n '1p')"
	case "$CORRECTNESS_OY_SELECTED_PLAN" in
		DUCKDB|OUTERYAN) ;;
		*) die "could not parse correctness-database OuterYan selected_plan" ;;
	esac
	printf 'correctness_outer_yan_selected_plan=%s\n' "$CORRECTNESS_OY_SELECTED_PLAN" \
		>> "$OUT_DIR/provenance/manifest.txt"
fi

CORRECTNESS_OK=1
CORRECTNESS_COMPARISONS="pgplan"
[ "$COMPARISON_MODE" != "both" ] || CORRECTNESS_COMPARISONS="$CORRECTNESS_COMPARISONS outer_yan"
for config in $CORRECTNESS_COMPARISONS; do
	if run_postprocess "$OUT_DIR/correctness/${config}.compare.stdout" \
			"$OUT_DIR/correctness/${config}.compare.stderr" \
			cmp -s "$OUT_DIR/correctness/native.sorted.records.jsonl" \
			"$OUT_DIR/correctness/${config}.sorted.records.jsonl"; then
		printf 'PASS native == %s\n' "$config" > "$OUT_DIR/correctness/${config}.comparison.txt"
	else
		rc=$?
		if [ "$rc" -ne 1 ]; then
			handle_postprocess_failure "$rc" \
				"$OUT_DIR/correctness/${config}.compare.stderr" \
				correctness_compare "$config" \
				"result multiset comparison failed for $config"
		fi
		CORRECTNESS_OK=0
		printf 'FAIL native != %s\n' "$config" > "$OUT_DIR/correctness/${config}.comparison.txt"
		# The complete sorted files are retained on a mismatch. Record only the
		# first differing byte/line instead of materializing an unbounded unified
		# diff that can be substantially larger than both inputs.
		if run_postprocess "$OUT_DIR/correctness/${config}.diff" \
				"$OUT_DIR/correctness/${config}.diff.stderr" \
				cmp "$OUT_DIR/correctness/native.sorted.records.jsonl" \
				"$OUT_DIR/correctness/${config}.sorted.records.jsonl"; then
			die "internal error: silent cmp reported a mismatch but diagnostic cmp did not"
		else
			diff_rc=$?
			case "$diff_rc" in
				1) ;;
				124)
					if [ "$TIMEOUT_SECS" -gt 0 ]; then
						printf 'First-difference diagnostic exceeded %ss.\n' \
							"$TIMEOUT_SECS" > "$OUT_DIR/correctness/${config}.diff.status.txt"
					else
						die "first-difference diagnostic failed for $config (exit=124)"
					fi
					;;
				*) die "first-difference diagnostic failed for $config (exit=$diff_rc)" ;;
			esac
		fi
	fi
done
[ "$CORRECTNESS_OK" -eq 1 ] || die "result multiset mismatch; timing was not run"
if [ "$COMPARISON_MODE" = "both" ]; then
	printf 'PASS: native, PGPlan, and OuterYan complete multisets are identical\n' \
		> "$OUT_DIR/correctness/status.txt"
else
	printf 'PARTIAL: native and PGPlan complete multisets are identical; OuterYan correctness was not run\n' \
		> "$OUT_DIR/correctness/status.txt"
fi
if MULTISET_SHA256="$(sha256_file \
		"$OUT_DIR/correctness/native.sorted.records.jsonl" 1 \
		2> "$OUT_DIR/correctness/multiset_hash.stderr")"; then
	:
else
	rc=$?
	handle_postprocess_failure "$rc" \
		"$OUT_DIR/correctness/multiset_hash.stderr" \
		correctness_hash native "multiset hashing failed"
fi
[ -n "$MULTISET_SHA256" ] || die "multiset hashing returned an empty digest"
printf 'sha256\trows\n%s\t%s\n' "$MULTISET_SHA256" \
	"$(awk -F '\t' '$1 == "native" {print $2}' "$OUT_DIR/correctness/row_counts.tsv")" \
	> "$OUT_DIR/correctness/multiset_sha256.tsv"
CORRECTNESS_ROWS="$(awk -F '\t' '$1 == "native" {print $2}' \
	"$OUT_DIR/correctness/row_counts.tsv")"
CORRECTNESS_SCOPE="$([ "$CORRECTNESS_DB" = "$EXECUTION_DB" ] && printf target || printf bounded)"
if [ "$COMPARISON_MODE" = "both" ] && [ "$CORRECTNESS_SCOPE" = "target" ]; then
	create_correctness_receipt
else
	if [ "$COMPARISON_MODE" = "both" ]; then
		CORRECTNESS_ORIGIN=FRESH
		CORRECTNESS_STATUS=PASS
		CORRECTNESS_SET=both
		printf 'No reusable receipt: complete correctness ran on a non-target database.\n' \
			> "$OUT_DIR/correctness/unsealed.txt"
	else
		CORRECTNESS_ORIGIN=PARTIAL
		CORRECTNESS_STATUS=PARTIAL
		CORRECTNESS_SET=pgplan-only
		printf 'No reusable receipt: OuterYan correctness was not executed.\n' \
			> "$OUT_DIR/correctness/unsealed.txt"
	fi
	{
		printf 'correctness_origin=%s\ncorrectness_status=%s\n' \
			"$CORRECTNESS_ORIGIN" "$CORRECTNESS_STATUS"
		printf 'correctness_comparison_executed=1\ncorrectness_comparison_set=%s\n' \
			"$CORRECTNESS_SET"
		printf 'correctness_scope=%s\ncorrectness_threads=%s\n' \
			"$CORRECTNESS_SCOPE" "$THREADS"
		printf 'correctness_rows=%s\ncorrectness_multiset_sha256=%s\n' \
			"$CORRECTNESS_ROWS" "$MULTISET_SHA256"
	} >> "$OUT_DIR/provenance/manifest.txt"
fi
if [ "$KEEP_CORRECTNESS_FILES" = "0" ]; then
	for config in $CORRECTNESS_CONFIGS; do
		rm -f -- \
			"$OUT_DIR/correctness/${config}.csv" \
			"$OUT_DIR/correctness/${config}.records.jsonl" \
			"$OUT_DIR/correctness/${config}.sorted.records.jsonl"
	done
	printf 'Large correctness files removed after full comparison; canonical hash retained.\n' \
		> "$OUT_DIR/correctness/storage_policy.txt"
fi
fi

# DuckDB's CLI timer reports one `real` sample for each bare-query statement.
# The first is the warm-up. Keep the raw log and select the middle measured
# sample only after checking that all N+1 executions completed.
extract_median() {
	local raw_file="$1" expected="$2"
	awk -v expected="$expected" '
		/Run Time/ {
			for (i = 1; i <= NF; i++) {
				if ($i == "real") samples[++count] = $(i + 1)
			}
		}
		END {
			if (count != expected + 1) exit 2
			for (i = 2; i <= count; i++) measured[i - 1] = samples[i] + 0
			for (i = 1; i <= expected; i++)
				for (j = i + 1; j <= expected; j++)
					if (measured[j] < measured[i]) {
						tmp = measured[i]; measured[i] = measured[j]; measured[j] = tmp
					}
			printf "%.9f", measured[(expected + 1) / 2]
		}
	' "$raw_file"
}

# Match experiment_onoff.sh's real timing atom exactly: each configuration runs
# in a fresh CLI process, profiling is disabled before `.timer on`, `.mode
# trash` fully drains the bare query without charging CSV rendering or output
# I/O, and the first CLI wall-clock sample is excluded as the warm-up.
run_timing_suite() {
	local suite="$1" timing_threads="$2" measured_runs="$3"
	local summary_file="$4" file_prefix="$5"
	local config timing_sql timing_base i rc median
	printf 'configuration\tmedian_seconds\tmeasured_runs\tthreads\n' > "$summary_file"
	for config in native pgplan outer_yan; do
		timing_base="${file_prefix}${config}"
		timing_sql="$WORK_DIR/timing_${timing_base}.sql"
		{
			printf '.timer off\n.mode trash\nCALL disable_profiling();\nPRAGMA threads=%s;\n' "$timing_threads"
			statement_timeout_sql
			config_sql "$config"
			printf '.timer on\n'
			emit_bare_query
			i=0
			while [ "$i" -lt "$measured_runs" ]; do
				emit_bare_query
				i=$((i + 1))
			done
		} > "$timing_sql"
		if run_duck "$timing_sql" "$OUT_DIR/timing/${timing_base}.stdout" \
				"$OUT_DIR/timing/${timing_base}.stderr" "$((measured_runs + 1))"; then
			:
		else
			rc=$?
			handle_duck_failure "$rc" "$OUT_DIR/timing/${timing_base}.stderr" \
				"$suite" "$config" "$config $suite batch failed"
		fi
		cat "$OUT_DIR/timing/${timing_base}.stdout" \
			"$OUT_DIR/timing/${timing_base}.stderr" > "$OUT_DIR/timing/${timing_base}.log"
		if ! median="$(extract_median "$OUT_DIR/timing/${timing_base}.log" "$measured_runs")"; then
			die "$config $suite log did not contain exactly $((measured_runs + 1)) samples"
		fi
		printf '%s\t%s\t%s\t%s\n' \
			"$config" "$median" "$measured_runs" "$timing_threads" >> "$summary_file"
	done
}

printf 'Timing one warm-up plus %s measured runs per configuration at threads=%s...\n' \
	"$RUNS" "$THREADS"
run_timing_suite timing "$THREADS" "$RUNS" "$OUT_DIR/timing/summary.tsv" ""

FINISHED_UTC="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
printf 'finished_utc=%s\nstatus=PASS\n' "$FINISHED_UTC" >> "$OUT_DIR/provenance/manifest.txt"
printf 'PASS. Artifacts: %s\n' "$OUT_DIR"
cat "$OUT_DIR/timing/summary.tsv"
