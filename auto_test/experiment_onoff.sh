#!/usr/bin/env bash
# ============================================================================
# experiment_onoff.sh  —  Experiment 2: whole-optimizer OuterYan OFF vs ON.
# Spec: test/optimizer/outer_yan/EXPERIMENT_OUTERYAN_ONOFF_DESIGN.md
#
# Times the SAME queries that compare_equal_batch.sh checks for correctness —
# the OuterYan equivalence corpus under outerjoin_query/equivalence/ (select_star
# + aggregation). One source of truth: a query is correctness-checked there and
# timed here, against the same R1..R10 + R/S/T/K schema (just scaled up).
#
# Per corpus query, IN THIS ORDER:
#   1. CORRECTNESS GATE — oy_equiv_check (ON==OFF on the bare query). A query that
#      is not equivalence-preserving (or crashes/times out) is NOT timed.
#   2. JOIN_REORDER — oy_regime: No (OuterYan keeps DuckDB's join order) vs
#      Yes (OuterYan reorders), from the §2.1 join-order signature.
#   3. TIMING — oy_time_min off vs on (threads=1, materialised CREATE TABLE AS).
#
# FAIR TIMING: each query is MEASURED OVER A WINDOW — repeated until cumulative
# wall time >= --min-secs, reporting the MIN per-run (least-perturbed). For
# headline numbers use a RELEASE --bin and a large --rscale (the deep chains then
# exceed ~2s/run; the smallest 3-relation shapes are sub-second by nature). The
# data generator keys joins per-id, so result size scales LINEARLY with --rscale.
#
# USAGE: experiment_onoff.sh [options]
#   -b,--bin PATH     duckdb (default build/release/duckdb, else build/debug)
#   -r,--rscale N     total_ids for R1..R10     (default 1000000)
#   -n,--runs N       min timed runs (floor)    (default 3)
#      --min-secs S   measurement window/query  (default 5; 0 = just --runs)
#   -t,--timeout S    per-query timeout sec      (default 300)
#      --only select|agg|all   which corpus dirs (default all)
#      --pattern GLOB  only queries whose label matches (default *)
#      --limit N       cap number of queries (0 = no cap, default 0)
#   -o,--out FILE     results file (default experiment_onoff_results.txt)
# ============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export DUCKDB_BIN="${DUCKDB_BIN:-$REPO_ROOT/build/release/duckdb}"
[ -x "$DUCKDB_BIN" ] || export DUCKDB_BIN="$REPO_ROOT/build/debug/duckdb"
DATAGEN="$SCRIPT_DIR/data_generation.py"
CORPUS="$SCRIPT_DIR/outerjoin_query/equivalence"

RSCALE=1000000; RUNS=3; ONLY="all"; PATTERN="*"; LIMIT=0; OUT=""
export OY_MIN_SECS=5; export OY_TIMEOUT_SECS=300
while [ $# -gt 0 ]; do case "$1" in
    -b|--bin) export DUCKDB_BIN="$2"; shift 2;;
    -r|--rscale) RSCALE="$2"; shift 2;;
    -n|--runs) RUNS="$2"; shift 2;;
    --min-secs) export OY_MIN_SECS="$2"; shift 2;;
    -t|--timeout) export OY_TIMEOUT_SECS="$2"; shift 2;;
    --only) ONLY="$2"; shift 2;;
    --pattern) PATTERN="$2"; shift 2;;
    --limit) LIMIT="$2"; shift 2;;
    -o|--out) OUT="$2"; shift 2;;
    -h|--help) sed -n '2,/^set /{/^set /q;p}' "${BASH_SOURCE[0]}"; exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 2;; esac; done
OUT="${OUT:-$REPO_ROOT/experiment_onoff_results.txt}"

[ -x "$DUCKDB_BIN" ] || { echo "Error: duckdb not executable: $DUCKDB_BIN" >&2; exit 1; }
case "$DUCKDB_BIN" in *debug*) echo "WARNING: timing a DEBUG build — directional only; pass --bin <release>." >&2;; esac
source "$SCRIPT_DIR/outer_yan_bench_lib.sh"

# --- collect the corpus queries (the same ON files compare_equal_batch runs) --
DIRS=()
case "$ONLY" in
    select) DIRS=("$CORPUS/select_star");;
    agg)    DIRS=("$CORPUS/aggregation");;
    all)    DIRS=("$CORPUS/select_star" "$CORPUS/aggregation");;
    *) echo "Unknown --only: $ONLY (select|agg|all)" >&2; exit 2;;
esac
LABELS=(); SQLS=()
for d in "${DIRS[@]}"; do
    for f in "$d"/*.sql; do
        case "$f" in *_off.sql) continue;; esac
        lbl="$(basename "$f" .sql)"
        case "$lbl" in $PATTERN) ;; *) continue;; esac
        LABELS+=("$lbl"); SQLS+=("$(cat "$f")")
        [ "$LIMIT" -gt 0 ] && [ "${#LABELS[@]}" -ge "$LIMIT" ] && break
    done
    [ "$LIMIT" -gt 0 ] && [ "${#LABELS[@]}" -ge "$LIMIT" ] && break
done
[ "${#LABELS[@]}" -gt 0 ] || { echo "No corpus queries matched (only=$ONLY pattern=$PATTERN)" >&2; exit 1; }

# --- build the timing database once (R1..R10 + R/S/T/K, scaled) --------------
DB="$(mktemp -u).duckdb"; TMPR="$(mktemp -d)"
trap 'rm -rf "$DB" "$DB".wal "$TMPR"' EXIT
echo "Generating R1..R10 (total_ids=$RSCALE) ..." >&2
python3 "$DATAGEN" --k 10 --total-ids "$RSCALE" --seed 42 --output-dir "$TMPR" >/dev/null \
    || { echo "data_generation.py failed" >&2; exit 1; }
echo "Loading R1..R10 + R/S/T/K views ..." >&2
{
  for i in $(seq 1 10); do
    echo "CREATE TABLE R$i AS SELECT * FROM read_csv('$TMPR/R$i.csv', header=false, columns={'src':'BIGINT','dst':'BIGINT'});"
  done
  echo "CREATE VIEW R AS SELECT * FROM R1; CREATE VIEW S AS SELECT * FROM R2;"
  echo "CREATE VIEW T AS SELECT * FROM R3; CREATE VIEW K AS SELECT * FROM R4;"
} | "$DUCKDB_BIN" "$DB" >/dev/null || { echo "schema build failed" >&2; exit 1; }
SIZES="$( { for i in $(seq 1 10); do echo "SELECT 'R$i=' || count(*) FROM R$i;"; done; } \
          | "$DUCKDB_BIN" "$DB" -noheader -list 2>/dev/null | paste -sd' ' - )"

# --- run: gate -> regime -> time, teed to $OUT -------------------------------
{
echo "# OuterYan on/off experiment   $(date '+%F %T')"
echo "# binary : $DUCKDB_BIN"
echo "# corpus : $ONLY  (pattern=$PATTERN limit=$LIMIT) — ${#LABELS[@]} queries from outerjoin_query/equivalence/"
echo "# tables : $SIZES"
echo "# timing : threads=1, materialised CREATE TABLE AS, MIN per-run over a >=${OY_MIN_SECS}s window (floor ${RUNS} runs)"
echo "# correct: ON result multiset == OFF result; only correct queries are timed"
echo

QN=0; NSKIP=0; NTIMED=0; NNO=0; NYES=0; SUMNO=0; SUMYES=0
QLBL=(); QNREL=(); QCORRECT=(); QNOTE=(); QROWS=(); QREG=(); QOFF=(); QON=(); QRATIO=(); QITERS=()

for ((i=0; i<${#LABELS[@]}; i++)); do
    id="${LABELS[i]}"; sql="${SQLS[i]}"
    nrel="-"; case "$id" in *_N[0-9]*) nrel="$(printf '%s' "$id" | sed -nE 's/.*_N([0-9]+)_.*/\1/p')";; esac
    gate="$(oy_equiv_check "$DB" "$id" "$sql")"
    case "$gate" in
        *"equiv OK"*)  correct="TRUE";  note="OK";        rows="$(printf '%s' "$gate" | grep -oE '[0-9]+ rows' | grep -oE '[0-9]+')";;
        *"NOT EQUIV"*) correct="FALSE"; note="NOT-EQUIV"; rows="$(printf '%s' "$gate" | grep -oE 'off=[0-9]+ on=[0-9]+')";;
        *"TIMEOUT"*)   correct="FALSE"; note="TIMEOUT";   rows="-";;
        *)             correct="FALSE"; note="ERROR";     rows="-";;
    esac
    reg="-"; off="-"; on="-"; ratio="-"; iters="-"
    if [ "$correct" = "TRUE" ]; then
        reg="$(oy_regime "$DB" "$sql")"; reg="${reg%% *}"
        local_ro="$(oy_time_min "$DB" "$OY_OFF" "$sql" "$RUNS" 1)"
        local_rn="$(oy_time_min "$DB" "$OY_ON"  "$sql" "$RUNS" 1)"
        off="$(echo "$local_ro" | awk '{print $1}')"; on="$(echo "$local_rn" | awk '{print $1}')"
        iters="$(echo "$local_ro" | awk '{print $2}')/$(echo "$local_rn" | awk '{print $2}')"
        ratio="$(awk -v a="$off" -v b="$on" 'BEGIN{ if(a!="NA"&&b!="NA"&&a+0>0) printf "%.3f", b/a; else print "NA" }')"
        NTIMED=$((NTIMED+1))
        if [ "$ratio" != "NA" ]; then
            if [ "$reg" = "No" ]; then NNO=$((NNO+1));  SUMNO="$(awk -v s="$SUMNO" -v r="$ratio" 'BEGIN{print s+r}')"
            else                       NYES=$((NYES+1)); SUMYES="$(awk -v s="$SUMYES" -v r="$ratio" 'BEGIN{print s+r}')"; fi
        fi
    else
        NSKIP=$((NSKIP+1))
    fi
    QLBL[$QN]="$id"; QNREL[$QN]="$nrel"; QCORRECT[$QN]="$correct"; QNOTE[$QN]="$note"; QROWS[$QN]="$rows"
    QREG[$QN]="$reg"; QOFF[$QN]="$off"; QON[$QN]="$on"; QRATIO[$QN]="$ratio"; QITERS[$QN]="$iters"
    QN=$((QN+1))
    printf '  [%3d/%d] %-34s correct=%-5s %s\n' "$QN" "${#LABELS[@]}" "$id" "$correct" "$note" >&2
done

# ---- Section 1: correctness catalog ----------------------------------------
echo "============================ QUERY CATALOG ============================"
printf '%-34s %-5s %-9s %-10s %s\n' query nrel correct note rows
echo "----------------------------------------------------------------------"
for ((j=0; j<QN; j++)); do
    printf '%-34s %-5s %-9s %-10s %s\n' "${QLBL[j]}" "${QNREL[j]}" "${QCORRECT[j]}" "${QNOTE[j]}" "${QROWS[j]}"
done

# ---- Section 2: timing (correct queries only) ------------------------------
echo
echo "===================== TIMING (correct queries) ========================"
printf '%-34s %-9s %10s %10s %8s %11s\n' query reorder? off\(s\) on\(s\) on/off it:off/on
echo "----------------------------------------------------------------------"
for ((j=0; j<QN; j++)); do
    [ "${QCORRECT[j]}" = "TRUE" ] || continue
    printf '%-34s %-9s %10s %10s %8s %11s\n' \
        "${QLBL[j]}" "${QREG[j]}" "${QOFF[j]}" "${QON[j]}" "${QRATIO[j]}" "${QITERS[j]}"
done

# ---- Section 3: summary ----------------------------------------------------
echo
MNO="$(awk -v s="$SUMNO" -v n="$NNO" 'BEGIN{print (n? s/n : "-")}')"
MYES="$(awk -v s="$SUMYES" -v n="$NYES" 'BEGIN{print (n? s/n : "-")}')"
echo "============================== SUMMARY ================================"
echo "queries=$QN  correct=$((QN-NSKIP))  incorrect/skipped=$NSKIP  timed=$NTIMED"
echo "  No  (no reorder): n=$NNO  mean on/off=$MNO   [expect >=1.0 — SJ overhead, no reorder]"
echo "  Yes (reorder):   n=$NYES  mean on/off=$MYES   [may be <1.0 — reorder/reduction win]"
} | tee "$OUT"
echo "Results written to $OUT"
