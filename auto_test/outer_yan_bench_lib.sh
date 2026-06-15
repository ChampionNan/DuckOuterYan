#!/usr/bin/env bash
# ============================================================================
# outer_yan_bench_lib.sh  —  shared primitives for the OuterYan experiments.
#
# Sourced by experiment_onoff.sh and experiment_semijoin.sh. It factors the
# OFF-vs-ON equivalence check into a REUSABLE, fully-parameterised atomic unit so
# every experiment can gate its measurements on query correctness FIRST:
#
#   oy_equiv_check <db> <label> <query>    the correctness atom (OFF vs ON)
#   oy_time_min    <db> <set_sql> <query> <runs> <threads>   min wall time
#   oy_regime      <db> <query>            join_reorder Yes/No via join-order signature
#
# The caller must export DUCKDB_BIN. Optional: OY_TIMEOUT_SECS (default 120,
# 0=off). All functions are bash-3.2 safe (no mapfile / associative arrays).
# ============================================================================

OY_OFF="SET disabled_optimizers TO 'outer_yan';"
OY_ON="SET disabled_optimizers TO '';"
: "${OY_TIMEOUT_SECS:=120}"
OY_TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
[ "${OY_TIMEOUT_SECS}" = "0" ] && OY_TIMEOUT_BIN=""

# Invoke duckdb, optionally under a timeout. A function (not a `${VAR:+...}`
# inline prefix, which does not word-split in zsh) so it is shell-portable and
# contributes a single, correct PIPESTATUS entry (124 on timeout).
oy_duck() {  # args after the db path are passed through; reads stdin
    if [ -n "$OY_TIMEOUT_BIN" ]; then
        "$OY_TIMEOUT_BIN" "$OY_TIMEOUT_SECS" "$DUCKDB_BIN" "$@"
    else
        "$DUCKDB_BIN" "$@"
    fi
}

# --- the correctness atom ---------------------------------------------------
# Runs the SAME query with OuterYan OFF and ON against <db>, sorts both result
# sets (multiset + order-independent) and diffs. Prints a verdict line.
# RETURNS: 0 PASS (ON==OFF) | 1 FAIL (rows differ) | 2 ERROR (crash) | 3 TIMEOUT.
# This is "compare the query equivalence by input parameters" — the atomic unit
# every experiment calls before it trusts a timing number.
oy_equiv_check() {
    local db="$1" label="$2" query="$3"
    local off on eoff eon roff ron rc=0
    off=$(mktemp); on=$(mktemp); eoff=$(mktemp); eon=$(mktemp)

    { echo "$OY_OFF"; echo "$query"; } \
        | oy_duck "$db" -csv -noheader 2>"$eoff" | LC_ALL=C sort > "$off"; roff=${PIPESTATUS[1]}
    { echo "$OY_ON";  echo "$query"; } \
        | oy_duck "$db" -csv -noheader 2>"$eon"  | LC_ALL=C sort > "$on";  ron=${PIPESTATUS[1]}

    if [ "${roff:-0}" -eq 124 ] || [ "${ron:-0}" -eq 124 ]; then
        echo "  ⏱️  TIMEOUT (${OY_TIMEOUT_SECS}s): $label"; rc=3
    elif grep -qE 'Error:' "$eoff"; then
        echo "  ⚠️  ERROR (off): $label"; grep -E 'Error:' "$eoff" | head -1 | sed 's/^/        /'; rc=2
    elif grep -qE 'Error:' "$eon"; then
        echo "  ⚠️  ERROR (on):  $label"; grep -E 'Error:' "$eon" | head -1 | sed 's/^/        /'; rc=2
    elif diff -q "$off" "$on" >/dev/null; then
        echo "  ✅ equiv OK: $label ($(wc -l < "$off" | tr -d ' ') rows)"; rc=0
    else
        echo "  ❌ NOT EQUIV: $label (off=$(wc -l < "$off" | tr -d ' ') on=$(wc -l < "$on" | tr -d ' '))"
        diff "$off" "$on" | head -6 | sed 's/^/        /'; rc=1
    fi
    rm -f "$off" "$on" "$eoff" "$eon"
    return $rc
}

# Compare TWO queries' result multisets under ONE config (the original
# compare_equal.sh two-query semantics — used to check a hand-written semi-join
# rewrite against the plain join). 0 equal | 1 differ | 2 error.
oy_equiv_two() {
    local db="$1" label="$2" set_sql="$3" qa="$4" qb="$5"
    local a b ea eb rc=0
    a=$(mktemp); b=$(mktemp); ea=$(mktemp); eb=$(mktemp)
    { echo "$set_sql"; echo "$qa"; } | oy_duck "$db" -csv -noheader 2>"$ea" | LC_ALL=C sort > "$a"
    { echo "$set_sql"; echo "$qb"; } | oy_duck "$db" -csv -noheader 2>"$eb" | LC_ALL=C sort > "$b"
    if grep -qE 'Error:' "$ea" "$eb"; then
        echo "  ⚠️  ERROR: $label"; grep -hE 'Error:' "$ea" "$eb" | head -1 | sed 's/^/        /'; rc=2
    elif diff -q "$a" "$b" >/dev/null; then
        echo "  ✅ equiv OK: $label ($(wc -l < "$a" | tr -d ' ') rows)"; rc=0
    else
        echo "  ❌ NOT EQUIV: $label (A=$(wc -l < "$a" | tr -d ' ') B=$(wc -l < "$b" | tr -d ' '))"; rc=1
    fi
    rm -f "$a" "$b" "$ea" "$eb"; return $rc
}

# --- timing -----------------------------------------------------------------
# Min wall time (seconds) of <query> materialised as CREATE OR REPLACE TEMP
# TABLE (forces the full plan with an identical sink; cancels client transfer).
#
# Fairness over noise: a single run of these shapes is often sub-10ms on a debug
# build, where process/scheduling jitter dominates. So we MEASURE OVER A WINDOW:
# the query is repeated until cumulative wall time >= OY_MIN_SECS (default 0 =
# just <runs>), and we report the MIN per-run over that window (the least-
# perturbed execution).
#
# PRINTS three space-separated fields: "<min_per_run_s> <iterations> <window_s>"
# (so the caller can show how the number was sampled — globals can't be used
# because callers invoke this via $(...), a subshell). On error: "NA 0 0".
: "${OY_MIN_SECS:=0}"

oy_time_min() {
    local db="$1" set_sql="$2" query="$3" runs="$4" threads="$5"
    # 1) warm-up: one run, also used to estimate the per-run time.
    local warm
    warm="$(printf 'PRAGMA threads=%s;\n%s\n.timer on\nCREATE OR REPLACE TEMP TABLE _oy_t AS %s;\n' \
                   "$threads" "$set_sql" "${query%;}" \
            | oy_duck "$db" 2>&1 \
            | awk '/Run Time/{for(i=1;i<=NF;i++) if($i=="real"){print $(i+1); exit}}')"
    [ -z "$warm" ] && { echo "NA 0 0"; return; }     # errored / timed out
    # 2) choose iteration count so the timed window >= OY_MIN_SECS (cap 20000).
    local K
    K="$(awk -v w="$warm" -v m="$OY_MIN_SECS" -v r="$runs" \
            'BEGIN{ k=r; if(m>0){k=int(m/(w>0?w:0.001))+1; if(k<r)k=r}; if(k>20000)k=20000; print k }')"
    # 3) timed batch of K runs in one session; min over the K creates (the final
    #    DROP also times, so keep only the first K lines). Prints "min iters window".
    local script i
    script="PRAGMA threads=${threads};"$'\n'"${set_sql}"$'\n'".timer on"$'\n'
    for ((i=0; i<K; i++)); do script+="CREATE OR REPLACE TEMP TABLE _oy_t AS ${query%;};"$'\n'; done
    script+="DROP TABLE IF EXISTS _oy_t;"$'\n'
    printf '%s' "$script" | oy_duck "$db" 2>&1 \
        | awk '/Run Time/{for(i=1;i<=NF;i++) if($i=="real") print $(i+1)}' \
        | awk -v K="$K" 'NR<=K{n++; s+=$1; if(min==""||$1+0<min+0) min=$1}
                         END{ if(n) printf "%s %d %.2f", min, n, s; else printf "NA 0 0" }'
}

# --- join-order signature (regime classification, design §2.1) --------------
# Canonical signature = sorted multiset of {base tables} under every join node
# of the physical plan (SJ_BUILD/SJ_PROBE skipped — pass-through). Two configs
# share a join ORDER iff their signatures match.
read -r -d '' OY_SIG_PY <<'PY'
import json,sys
raw=sys.stdin.read()
i,j=raw.find('['),raw.rfind(']')
if i<0 or j<0: print("NOSIG"); sys.exit(0)
try: data=json.loads(raw[i:j+1])
except Exception: print("BADSIG"); sys.exit(0)
def tabs(n,acc):
    ei=n.get("extra_info") or {}
    for key in ("Table","Text"):
        v=ei.get(key)
        if isinstance(v,str) and v: acc.add(v); break
    for c in (n.get("children") or []): tabs(c,acc)
sigs=[]
def walk(n):
    nm=(n.get("name") or "").upper()
    kids=n.get("children") or []
    if "JOIN" in nm and "SJ_" not in nm:
        s=set()
        for c in kids: tabs(c,s)
        if s: sigs.append("{"+",".join(sorted(s))+"}")
    for c in kids: walk(c)
for r in (data if isinstance(data,list) else [data]): walk(r)
print("|".join(sorted(sigs)) if sigs else "NOJOIN")
PY

oy_sig() {  # $1=db $2=set_sql $3=query  -> canonical signature string
    { echo "$2"; echo "EXPLAIN (FORMAT json) ${3%;};"; } \
        | "$DUCKDB_BIN" "$1" -list -noheader 2>/dev/null | python3 -c "$OY_SIG_PY"
}

# Prints "No sj=<yes|no>" or "Yes sj=<yes|no>" (join_reorder?): No ⇔ ON order == OFF order.
oy_regime() {
    local db="$1" query="$2" s_off s_on sj
    s_off="$(oy_sig "$db" "$OY_OFF" "$query")"
    s_on="$(oy_sig  "$db" "$OY_ON"  "$query")"
    if { echo "$OY_ON"; echo "EXPLAIN (FORMAT json) ${query%;};"; } \
        | "$DUCKDB_BIN" "$db" -list -noheader 2>/dev/null | grep -q 'SJ_PROBE'; then
        sj="yes"; else sj="no"; fi
    if [ "$s_off" = "$s_on" ]; then echo "No sj=$sj"; else echo "Yes sj=$sj"; fi
}
