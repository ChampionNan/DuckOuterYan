#!/bin/bash
# Compare a query's result with OuterYan OFF vs ON by OUTPUT DIFF (sorted, so
# multiset + order-independent). Clearer than the in-test sym_diff macro.
# Usage: compare_onoff.sh <duckdb_bin> <prelude_sql_file> <query_sql_file>
DB="$1"; PRE="$2"; Q="$3"
off=$(mktemp); on=$(mktemp); eoff=$(mktemp); eon=$(mktemp)
{ cat "$PRE"; echo "SET disabled_optimizers TO 'outer_yan';"; cat "$Q"; } | "$DB" -csv -noheader 2>"$eoff" | sort > "$off"
{ cat "$PRE"; echo "SET disabled_optimizers TO '';";          cat "$Q"; } | "$DB" -csv -noheader 2>"$eon"  | sort > "$on"
if grep -qi "error" "$eoff" "$eon"; then echo "ERROR: $(grep -i error "$eoff" "$eon" | head -1)"; rm -f "$off" "$on" "$eoff" "$eon"; exit 2; fi
if diff -q "$off" "$on" >/dev/null; then echo "IDENTICAL ($(wc -l < "$off") rows)"; rm -f "$off" "$on" "$eoff" "$eon"; exit 0
else echo "DIFFER (off=$(wc -l < "$off") on=$(wc -l < "$on"))"; diff "$off" "$on" | head -8; rm -f "$off" "$on" "$eoff" "$eon"; exit 1; fi
