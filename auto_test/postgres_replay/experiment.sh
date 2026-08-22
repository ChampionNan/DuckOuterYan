#!/usr/bin/env bash
# Compare DuckDB's native join tree, PostgreSQL's logical tree (PGPlan), and
# OuterYan. Correctness always runs before timing and always executes the bare
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
  --runs N            Positive odd measured-run count after one warm-up
                      (PGPLAN_RUNS, default: 3)
  --threads N         Positive DuckDB thread count
                      (PGPLAN_THREADS, default: 1)
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

The output directory receives plans, complete sorted result multisets, traces,
settings, timing logs, and copies/hashes of the query and PostgreSQL artifact.
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
QUERY_PATH="${PGPLAN_QUERY:-${PG_REPLAY_QUERY:-}}"
PLAN_PATH="${PGPLAN_PLAN:-${PG_REPLAY_PLAN:-}}"
OUT_DIR="${PGPLAN_OUT:-${PG_REPLAY_OUT:-}}"
RUNS="${PGPLAN_RUNS:-${PG_REPLAY_RUNS:-3}}"
THREADS="${PGPLAN_THREADS:-${PG_REPLAY_THREADS:-1}}"
TIMEOUT_SECS="${PGPLAN_TIMEOUT_SECS:-${PG_REPLAY_TIMEOUT_SECS:-0}}"
TIMEOUT_GRACE="${PGPLAN_TIMEOUT_GRACE:-${PG_REPLAY_TIMEOUT_GRACE:-30}}"
KEEP_CORRECTNESS_FILES="${PGPLAN_KEEP_CORRECTNESS_FILES:-1}"

while [ "$#" -gt 0 ]; do
	case "$1" in
		--duckdb-bin)
			require_value "$@"; DUCKDB_BIN="$2"; shift 2 ;;
		--execution-db)
			require_value "$@"; EXECUTION_DB="$2"; shift 2 ;;
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
[ -n "$QUERY_PATH" ] || usage_error "--query is required"
[ -n "$PLAN_PATH" ] || usage_error "--plan is required"
[ -n "$OUT_DIR" ] || usage_error "--out is required"

case "$RUNS" in ''|*[!0-9]*|0) usage_error "--runs must be a positive integer" ;; esac
[ $((RUNS % 2)) -eq 1 ] || usage_error "--runs must be odd"
case "$THREADS" in ''|*[!0-9]*|0) usage_error "--threads must be a positive integer" ;; esac
case "$TIMEOUT_SECS" in ''|*[!0-9]*) usage_error "PGPLAN_TIMEOUT_SECS must be a non-negative integer" ;; esac
case "$TIMEOUT_GRACE" in ''|*[!0-9]*) usage_error "PGPLAN_TIMEOUT_GRACE must be a non-negative integer" ;; esac
case "$KEEP_CORRECTNESS_FILES" in 0|1) ;; *) usage_error "PGPLAN_KEEP_CORRECTNESS_FILES must be 0 or 1" ;; esac

[ -x "$DUCKDB_BIN" ] || die "DuckDB binary is not executable: $DUCKDB_BIN"
[ -f "$EXECUTION_DB" ] || die "execution database does not exist: $EXECUTION_DB"
[ -r "$QUERY_PATH" ] || die "query file is not readable: $QUERY_PATH"
[ -r "$PLAN_PATH" ] || die "plan artifact is not readable: $PLAN_PATH"
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
QUERY_PATH="$(canonical_file "$QUERY_PATH")"
PLAN_PATH="$(canonical_file "$PLAN_PATH")"
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

# run_duck SQL STDOUT STDERR MULTIPLIER [OY_TRACE]
# MULTIPLIER is N+1 for a warm-up plus N measured executions. SQL also carries
# the per-statement limit; this outer watchdog only prevents a wedged process.
run_duck() {
	local sql_file="$1" stdout_file="$2" stderr_file="$3" multiplier="$4"
	local oy_trace="${5:-}" watchdog=0
	local -a command
	command=("$DUCKDB_BIN" -no-init -bail "$EXECUTION_DB")
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
	local digest_field=1
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
		"${command[@]}" | awk '{print $1}'
	else
		"${command[@]}" | awk '{print $NF}'
	fi
}

cp -- "$PLAN_PATH" "$OUT_DIR/provenance/postgres_plan.json"
QUERY_SHA256="$(sha256_file "$OUT_DIR/provenance/query.sql")"
PLAN_SHA256="$(sha256_file "$OUT_DIR/provenance/postgres_plan.json")"
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
	printf 'description=%s\n' "PostgreSQL 16.2's $PLAN_DATA-selected logical join tree, executed by DuckDB on the target-scale dataset."
	printf 'started_utc=%s\n' "$STARTED_UTC"
	printf 'duckdb_bin=%s\nexecution_db=%s\nquery=%s\nplan_source=%s\npgplan=%s\n' \
		"$DUCKDB_BIN" "$EXECUTION_DB" "$QUERY_PATH" "$PLAN_PATH" "$PGPLAN_PLAN_PATH"
	printf 'query_sha256=%s\nplan_sha256=%s\nruns=%s\nthreads=%s\n' \
		"$QUERY_SHA256" "$PLAN_SHA256" "$RUNS" "$THREADS"
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

printf 'Checking complete result multisets (bare query, external CSV sort)...\n'
printf 'configuration\trows\n' > "$OUT_DIR/correctness/row_counts.tsv"
for config in native pgplan outer_yan; do
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
			"$OUT_DIR/correctness/${config}.stderr" 1 "$OY_TRACE"; then
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

CORRECTNESS_OK=1
for config in pgplan outer_yan; do
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
printf 'PASS: native, PGPlan, and OuterYan complete multisets are identical\n' > "$OUT_DIR/correctness/status.txt"
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
if [ "$KEEP_CORRECTNESS_FILES" = "0" ]; then
	for config in native pgplan outer_yan; do
		rm -f -- \
			"$OUT_DIR/correctness/${config}.csv" \
			"$OUT_DIR/correctness/${config}.records.jsonl" \
			"$OUT_DIR/correctness/${config}.sorted.records.jsonl"
	done
	printf 'Large correctness files removed after full comparison; canonical hash retained.\n' \
		> "$OUT_DIR/correctness/storage_policy.txt"
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

printf 'Timing one warm-up plus %s measured runs per configuration...\n' "$RUNS"
printf 'configuration\tmedian_seconds\tmeasured_runs\tthreads\n' > "$OUT_DIR/timing/summary.tsv"
for config in native pgplan outer_yan; do
	TIMING_SQL="$WORK_DIR/timing_${config}.sql"
	{
		printf '.timer off\n.mode trash\nCALL disable_profiling();\nPRAGMA threads=%s;\n' "$THREADS"
		statement_timeout_sql
		config_sql "$config"
		printf '.timer on\n'
		emit_bare_query
		i=0
		while [ "$i" -lt "$RUNS" ]; do
			emit_bare_query
			i=$((i + 1))
		done
	} > "$TIMING_SQL"
	if run_duck "$TIMING_SQL" "$OUT_DIR/timing/${config}.stdout" \
			"$OUT_DIR/timing/${config}.stderr" "$((RUNS + 1))"; then
		:
	else
		rc=$?
		handle_duck_failure "$rc" "$OUT_DIR/timing/${config}.stderr" \
			timing "$config" "$config timing batch failed"
	fi
	cat "$OUT_DIR/timing/${config}.stdout" "$OUT_DIR/timing/${config}.stderr" > "$OUT_DIR/timing/${config}.log"
	if ! MEDIAN="$(extract_median "$OUT_DIR/timing/${config}.log" "$RUNS")"; then
		die "$config timing log did not contain exactly $((RUNS + 1)) samples"
	fi
	printf '%s\t%s\t%s\t%s\n' "$config" "$MEDIAN" "$RUNS" "$THREADS" >> "$OUT_DIR/timing/summary.tsv"
done

FINISHED_UTC="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
printf 'finished_utc=%s\nstatus=PASS\n' "$FINISHED_UTC" >> "$OUT_DIR/provenance/manifest.txt"
printf 'PASS. Artifacts: %s\n' "$OUT_DIR"
cat "$OUT_DIR/timing/summary.tsv"
