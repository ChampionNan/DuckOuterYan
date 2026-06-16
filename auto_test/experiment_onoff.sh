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
#   -t,--timeout S    soft per-query timeout sec  (default 300; via `timeout`)
#      --kill-after S hard SIGKILL any duckdb query running > S sec (default 300,
#                     5 min; 0 = off) — the backstop when a deadlock ignores --timeout
#      --only select|agg|pred|tpch|tpcds|equiv|bench|all  query families (default all);
#                     tpch/tpcds time against tpch_db/tpcds_db (TPCH_SF/TPCDS_SF env)
#      --pattern GLOB  only queries whose label matches (default *)
#      --exclude GLOB  skip labels matching any '|'-separated glob (prune slow shapes)
#      --limit N       cap number of queries (0 = no cap, default 0)
#   -o,--out FILE     results file (default experiment_onoff_results.txt)
# ============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export DUCKDB_BIN="${DUCKDB_BIN:-$REPO_ROOT/build/release/duckdb}"
[ -x "$DUCKDB_BIN" ] || export DUCKDB_BIN="$REPO_ROOT/build/debug/duckdb"
DATAGEN="$SCRIPT_DIR/data_generation.py"
CORPUS="$SCRIPT_DIR/outerjoin_query"
TPCH_SF="${TPCH_SF:-1}"; TPCDS_SF="${TPCDS_SF:-1}"      # scale for the tpch/tpcds families

RSCALE=1000000; RUNS=3; ONLY="all"; PATTERN="*"; EXCLUDE=""; LIMIT=0; OUT=""; KILL_AFTER=300
export OY_MIN_SECS=5; export OY_TIMEOUT_SECS=300
while [ $# -gt 0 ]; do case "$1" in
    -b|--bin) export DUCKDB_BIN="$2"; shift 2;;
    -r|--rscale) RSCALE="$2"; shift 2;;
    -n|--runs) RUNS="$2"; shift 2;;
    --min-secs) export OY_MIN_SECS="$2"; shift 2;;
    -t|--timeout) export OY_TIMEOUT_SECS="$2"; shift 2;;
    --kill-after) KILL_AFTER="$2"; shift 2;;
    --only) ONLY="$2"; shift 2;;
    --pattern) PATTERN="$2"; shift 2;;
    --exclude) EXCLUDE="$2"; shift 2;;
    --limit) LIMIT="$2"; shift 2;;
    -o|--out) OUT="$2"; shift 2;;
    -h|--help) sed -n '2,/^set /p' "${BASH_SOURCE[0]}"; exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 2;; esac; done
OUT="${OUT:-$REPO_ROOT/experiment_onoff_results.txt}"

[ -x "$DUCKDB_BIN" ] || { echo "Error: duckdb not executable: $DUCKDB_BIN" >&2; exit 1; }
case "$DUCKDB_BIN" in *debug*) echo "WARNING: timing a DEBUG build — directional only; pass --bin <release>." >&2;; esac
source "$SCRIPT_DIR/outer_yan_bench_lib.sh"

# --- hard watchdog: SIGKILL any of our duckdb queries running > KILL_AFTER secs.
# The soft --timeout uses `timeout`, which a DEADLOCKED duckdb can ignore (it then
# stalls the whole run); this is the reliable backstop. --kill-after 0 disables it.
_oy_watchdog() {  # $1=binary  $2=max-secs
    local pid e d rest p1 p2 p3 h m s sec
    while true; do
        for pid in $(pgrep -f "$1" 2>/dev/null); do
            e="$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')"; [ -z "$e" ] && continue
            d=0; rest="$e"; case "$e" in *-*) d="${e%%-*}"; rest="${e#*-}";; esac
            IFS=: read -r p1 p2 p3 <<< "$rest"
            if [ -n "$p3" ]; then h=$p1; m=$p2; s=$p3; else h=0; m=$p1; s=$p2; fi
            sec=$((10#${d:-0}*86400 + 10#${h:-0}*3600 + 10#${m:-0}*60 + 10#${s:-0}))
            [ "$sec" -gt "$2" ] && kill -9 "$pid" 2>/dev/null \
                && echo "  [watchdog] SIGKILL $(basename "$1") pid=$pid etime=$e (>$2s)" >&2
        done
        sleep 15
    done
}
WATCHDOG_PID=""
if [ "${KILL_AFTER:-0}" -gt 0 ] 2>/dev/null; then
    _oy_watchdog "$DUCKDB_BIN" "$KILL_AFTER" & WATCHDOG_PID=$!
    echo "Hard query watchdog: SIGKILL duckdb running > ${KILL_AFTER}s (--kill-after)" >&2
fi

# --- families -> dirs + per-family DB (the SAME corpus compare_equal_batch runs) -
case "$ONLY" in
    select) FAMS="select";;       agg) FAMS="agg";;       pred) FAMS="pred";;
    tpch)   FAMS="tpch";;          tpcds) FAMS="tpcds";;
    equiv)  FAMS="select agg pred";;   bench) FAMS="tpch tpcds";;
    all)    FAMS="select agg pred tpch tpcds";;
    *) echo "Unknown --only: $ONLY (select|agg|pred|tpch|tpcds|equiv|bench|all)" >&2; exit 2;;
esac
need_equiv=0; need_tpch=0; need_tpcds=0
for fam in $FAMS; do case "$fam" in select|agg|pred) need_equiv=1;; tpch) need_tpch=1;; tpcds) need_tpcds=1;; esac; done

EQUIV_DB=""; TMPR=""; TPCH_DB="$REPO_ROOT/tpch_db"; TPCDS_DB="$REPO_ROOT/tpcds_db"
trap 'rm -rf "$EQUIV_DB" "$EQUIV_DB".wal "$TMPR"; [ -n "$WATCHDOG_PID" ] && kill "$WATCHDOG_PID" 2>/dev/null' EXIT

# equiv DB: scaled R1..R10 + R/S/T/K views (timing scale via --rscale)
if [ "$need_equiv" = 1 ]; then
    EQUIV_DB="$(mktemp -u).duckdb"; TMPR="$(mktemp -d)"
    echo "Generating R1..R10 (total_ids=$RSCALE) ..." >&2
    python3 "$DATAGEN" --k 10 --total-ids "$RSCALE" --seed 42 --output-dir "$TMPR" >/dev/null \
        || { echo "data_generation.py failed" >&2; exit 1; }
    { for i in $(seq 1 10); do
        echo "CREATE TABLE R$i AS SELECT * FROM read_csv('$TMPR/R$i.csv', header=false, columns={'src':'BIGINT','dst':'BIGINT'});"; done
      echo "CREATE VIEW R AS SELECT * FROM R1; CREATE VIEW S AS SELECT * FROM R2;"
      echo "CREATE VIEW T AS SELECT * FROM R3; CREATE VIEW K AS SELECT * FROM R4;"
    } | "$DUCKDB_BIN" "$EQUIV_DB" >/dev/null || { echo "equiv schema build failed" >&2; exit 1; }
fi
# tpch / tpcds DBs: built once, reused (scale via TPCH_SF / TPCDS_SF env)
if [ "$need_tpch" = 1 ] && [ ! -f "$TPCH_DB" ]; then
    echo "Building tpch_db (dbgen sf=$TPCH_SF) ..." >&2
    "$DUCKDB_BIN" "$TPCH_DB" -c "CALL dbgen(sf=$TPCH_SF);" >/dev/null 2>&1 \
        || { echo "WARNING: dbgen unavailable — tpch family skipped" >&2; need_tpch=0; rm -f "$TPCH_DB" "$TPCH_DB".wal; }
fi
if [ "$need_tpcds" = 1 ] && [ ! -f "$TPCDS_DB" ]; then
    echo "Building tpcds_db (dsdgen sf=$TPCDS_SF) ..." >&2
    "$DUCKDB_BIN" "$TPCDS_DB" -c "CALL dsdgen(sf=$TPCDS_SF);" >/dev/null 2>&1 \
        || { echo "WARNING: dsdgen unavailable — tpcds family skipped" >&2; need_tpcds=0; rm -f "$TPCDS_DB" "$TPCDS_DB".wal; }
fi

# --- collect queries, each tagged with its family DB -------------------------
LABELS=(); SQLS=(); DBS=()
for fam in $FAMS; do
    case "$fam" in
        select) dir="$CORPUS/equivalence/select_star"; fdb="$EQUIV_DB";;
        agg)    dir="$CORPUS/equivalence/aggregation";  fdb="$EQUIV_DB";;
        pred)   dir="$CORPUS/equivalence/predicates";   fdb="$EQUIV_DB";;
        tpch)   [ "$need_tpch"  = 1 ] || continue; dir="$CORPUS/tpch";  fdb="$TPCH_DB";;
        tpcds)  [ "$need_tpcds" = 1 ] || continue; dir="$CORPUS/tpcds"; fdb="$TPCDS_DB";;
    esac
    for f in "$dir"/*.sql; do
        case "$f" in *_off.sql) continue;; esac
        lbl="$(basename "$f" .sql)"
        case "$lbl" in $PATTERN) ;; *) continue;; esac
        if [ -n "$EXCLUDE" ]; then                       # prune: skip labels matching any |-glob
            _skip=0; IFS='|' read -ra _ex <<< "$EXCLUDE"
            for _g in "${_ex[@]}"; do case "$lbl" in $_g) _skip=1; break;; esac; done
            [ "$_skip" = 1 ] && continue
        fi
        LABELS+=("$lbl"); SQLS+=("$(cat "$f")"); DBS+=("$fdb")
        [ "$LIMIT" -gt 0 ] && [ "${#LABELS[@]}" -ge "$LIMIT" ] && break
    done
    [ "$LIMIT" -gt 0 ] && [ "${#LABELS[@]}" -ge "$LIMIT" ] && break
done
[ "${#LABELS[@]}" -gt 0 ] || { echo "No corpus queries matched (only=$ONLY pattern=$PATTERN)" >&2; exit 1; }
SIZES="families=[$FAMS]  equiv rscale=$RSCALE  tpch sf=$TPCH_SF  tpcds sf=$TPCDS_SF"

# --- run: gate -> regime -> time, teed to $OUT -------------------------------
{
echo "# OuterYan on/off experiment   $(date '+%F %T')"
echo "# binary : $DUCKDB_BIN"
echo "# corpus : $ONLY  (pattern=$PATTERN limit=$LIMIT) — ${#LABELS[@]} queries from outerjoin_query/"
echo "# tables : $SIZES"
echo "# timing : threads=1, materialised CREATE TABLE AS, MIN per-run over a >=${OY_MIN_SECS}s window (floor ${RUNS} runs)"
echo "# correct: ON result multiset == OFF result; only correct queries are timed"
echo

QN=0; NSKIP=0; NTIMED=0; NNO=0; NYES=0; SUMNO=0; SUMYES=0
QLBL=(); QNREL=(); QCORRECT=(); QNOTE=(); QROWS=(); QREG=(); QOFF=(); QON=(); QRATIO=(); QITERS=()

for ((i=0; i<${#LABELS[@]}; i++)); do
    id="${LABELS[i]}"; sql="${SQLS[i]}"; db="${DBS[i]}"
    nrel="-"; case "$id" in *_N[0-9]*) nrel="$(printf '%s' "$id" | sed -nE 's/.*_N([0-9]+)_.*/\1/p')";; esac
    gate="$(oy_equiv_check "$db" "$id" "$sql")"
    case "$gate" in
        *"equiv OK"*)  correct="TRUE";  note="OK";        rows="$(printf '%s' "$gate" | grep -oE '[0-9]+ rows' | grep -oE '[0-9]+')";;
        *"NOT EQUIV"*) correct="FALSE"; note="NOT-EQUIV"; rows="$(printf '%s' "$gate" | grep -oE 'off=[0-9]+ on=[0-9]+')";;
        *"TIMEOUT"*)   correct="FALSE"; note="TIMEOUT";   rows="-";;
        *)             correct="FALSE"; note="ERROR";     rows="-";;
    esac
    reg="-"; off="-"; on="-"; ratio="-"; iters="-"
    if [ "$correct" = "TRUE" ]; then
        reg="$(oy_regime "$db" "$sql")"; reg="${reg%% *}"
        local_ro="$(oy_time_min "$db" "$OY_OFF" "$sql" "$RUNS" 1)"
        local_rn="$(oy_time_min "$db" "$OY_ON"  "$sql" "$RUNS" 1)"
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
