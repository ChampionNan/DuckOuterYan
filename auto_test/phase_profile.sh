#!/usr/bin/env bash
# Shared profiling helpers sourced by experiment_onoff.sh, not a standalone CLI.
# oy_warm_profile_time runs warm-up -> optional profile -> unprofiled timing per side.
# oy_phase_profile_from_json reads CPU components from that same ON profile;
# it does not rerun the query. CPU work and wall latency remain separate.

# Read R1/R2/R3 operator work from the same post-warm-up ON execution used for
# optimizer timing. No query is executed here.
oy_phase_profile_from_json() {
    local profile_json="$1" query="$2" expected_plan="$3"
    local expected_r1_pairs="$4" expected_r2_pairs="$5" proven_empty="$6"
    "${PYTHON_BIN:-python3}" - "$profile_json" "${query%;}" "$expected_plan" \
        "$expected_r1_pairs" "$expected_r2_pairs" "$proven_empty" <<'PY'
import json
import math
import sys

path, expected_query, expected_plan, r1_text, r2_text, proven_empty_text = sys.argv[1:]
failure = "NA " * 14 + "NA"


def normalize_query(value):
    lines = value.strip().splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
        lines.pop(0)
    return " ".join("\n".join(lines).strip().rstrip(";").split())


def to_ns(value, label):
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"invalid {label} value {value!r}")
    return int(round(parsed * 1_000_000_000))


try:
    with open(path, encoding="utf-8") as handle:
        root = json.load(handle)
    missing = sorted({"query_name", "latency", "cpu_time", "children"}.difference(root))
    if missing:
        raise ValueError(f"profile is missing keys: {', '.join(missing)}")
    if normalize_query(root["query_name"]) != normalize_query(expected_query):
        raise ValueError("profile query_name does not match")
    if expected_plan not in ("DUCKDB", "OUTERYAN") or proven_empty_text not in ("0", "1"):
        raise ValueError("invalid expected plan metadata")
    expected_pairs = (int(r1_text), int(r2_text)) if expected_plan == "OUTERYAN" else (0, 0)
    if min(expected_pairs) < 0:
        raise ValueError("negative planned pair count")

    join_types = {
        "BLOCKWISE_NL_JOIN", "NESTED_LOOP_JOIN", "HASH_JOIN", "CROSS_PRODUCT",
        "PIECEWISE_MERGE_JOIN", "IE_JOIN", "LEFT_DELIM_JOIN", "RIGHT_DELIM_JOIN",
        "POSITIONAL_JOIN", "ASOF_JOIN",
    }
    round_names = (
        {"SJ_BUILD_ROUND_1", "SJ_PROBE_ROUND_1"},
        {"SJ_BUILD_ROUND_2", "SJ_PROBE_ROUND_2"},
    )
    totals = [0, 0, 0]
    counts = [0, 0, 0]

    def visit(node):
        name = node.get("operator_name")
        operator_type = node.get("operator_type")
        if not isinstance(name, str) or not isinstance(operator_type, str):
            raise ValueError("profile operator identity is missing")
        elapsed = to_ns(node.get("operator_timing"), f"operator_timing for {name!r}")
        phase = None
        if name in round_names[0]:
            phase = 0
        elif name in round_names[1]:
            phase = 1
        elif operator_type in join_types:
            phase = 2
        if phase is not None:
            totals[phase] += elapsed
            counts[phase] += 1
        for child in node.get("children", []):
            visit(child)

    for child in root["children"]:
        visit(child)

    if expected_plan == "DUCKDB" and any(totals[:2] + counts[:2]):
        raise ValueError("DuckDB plan unexpectedly executed a semi-join phase")
    if proven_empty_text == "0" and counts[2] == 0:
        raise ValueError("non-empty join plan has no R3 operator")
    if expected_plan == "OUTERYAN" and proven_empty_text == "0":
        for label, pairs, elapsed, operators in zip(("R1", "R2"), expected_pairs, totals[:2], counts[:2]):
            if pairs == 0 and (elapsed or operators):
                raise ValueError(f"{label} ran with zero planned pairs")
            if pairs > 0 and operators == 0:
                raise ValueError(f"{label} has planned pairs but did not run")

    wall = to_ns(root["latency"], "latency")
    cpu = to_ns(root["cpu_time"], "cpu_time")
    if wall <= 0 or cpu <= 0:
        raise ValueError("profile has non-positive latency or CPU time")
    component_total = sum(totals)
    if component_total > cpu:
        tolerance = max(1, sum(counts) + 1)
        if component_total - cpu > tolerance:
            raise ValueError("classified operator work exceeds CPU time")
        cpu = component_total
    other = cpu - component_total
    scale = 1_000_000_000
    units = [value * scale // cpu for value in totals]
    other_units = scale - sum(units)

    def seconds(value):
        return f"{value / scale:.9f}"

    def ratio(value):
        return f"{value // scale}.{value % scale:09d}"

    print("{} {} {} {} {} {} {} {} {} {} {} {} {} {} 1".format(
        seconds(totals[0]), seconds(totals[1]), seconds(totals[2]), seconds(wall), seconds(cpu),
        ratio(units[0]), ratio(units[1]), ratio(units[0] + units[1]), ratio(units[2]),
        seconds(other), ratio(other_units), counts[0], counts[1], counts[2]))
except Exception as exc:
    print(f"PROFILE-ERROR: {exc}", file=sys.stderr)
    print(failure)
    sys.exit(1)
PY
}

# One CLI per configuration preserves its own warmed buffer pool. Only statements
# after .timer on contribute to runtime. Profiler trace output is enabled only
# while the native profiler is enabled (requires the matching rebuilt binary).
# Echoes the timed sample (or median for explicit runs > 1) and sample count.
oy_warm_profile_time() {
    local db="$1" setting="$2" query="$3" threads="$4" runs="$5"
    local profiledir="$6" mode="$7" profile="$8"
    local sqlf rawf profilef tracef rc=0 saved_to="$OY_TIMEOUT_SECS" i
    sqlf=$(mktemp) || return 1
    rawf="$profiledir/optimizer_${mode}.log"
    profilef="$profiledir/optimizer_${mode}_1.json"
    tracef="$profiledir/optimizer_${mode}.trace"
    : > "$tracef"
    {
        printf ".timer off\n.mode trash\nCALL disable_profiling();\nPRAGMA threads=%s;\n%s\n%s\n" \
            "$threads" "$(oy_statement_timeout_sql "$OY_TIMEOUT_SECS")" "$setting"
        printf '.print OY_STAGE:warmup\n%s;\n' "${query%;}"
        if [ "$profile" = 1 ]; then
            printf ".print OY_STAGE:profile\nCALL enable_profiling(format='json', save_location='%s', coverage='select', mode='detailed');\n%s;\n" \
                "${profilef//"'"/"''"}" "${query%;}"
            # Unlike CALL, this pragma disables profiling before optimization
            # and cannot append an unrelated CALL decision to the profile trace.
            printf 'PRAGMA disable_profiling;\n'
        fi
        printf '.print OY_STAGE:timing\n.timer on\n'
        for ((i=0; i<runs; i++)); do printf '%s;\n' "${query%;}"; done
        printf '.timer off\n'
    } > "$sqlf"
    [ -n "$OY_TIMEOUT_BIN" ] && [ "$OY_TIMEOUT_SECS" != 0 ] \
        && OY_TIMEOUT_SECS=$(( saved_to * (1 + profile + runs) + OY_BATCH_GRACE_SECS ))
    # This helper is called in a command substitution; do not inherit verbose
    # traces or kernel diagnostics into the measured execution.
    unset DUCKDB_OYTRACE DUCKDB_SJ_KERNEL_TRACE
    DUCKDB_OY_PROFILE_TRACE="$tracef" oy_duck "$db" -noheader < "$sqlf" > "$rawf" 2>&1 || rc=$?
    OY_TIMEOUT_SECS="$saved_to"
    rm -f "$sqlf"
    if [ "$rc" -eq 124 ] || grep -qiE 'Error:.*(maximum execution time|timeout|interrupt)' "$rawf"; then
        echo "NA 0"; return 124
    fi
    if [ "$rc" -ne 0 ] || grep -q 'Error:' "$rawf"; then
        echo "NA 0"; return 1
    fi
    if [ "$mode" = outeryan ]; then
        local records
        records="$(awk '/^\[OY_DECISION\]/ {n++} END {print n+0}' "$tracef")"
        if [ "$records" != "$profile" ]; then
            printf 'Error: expected %s profile-only decisions, found %s; rebuild DuckDB before timing\n' \
                "$profile" "$records" >> "$rawf"
            echo "NA 0"; return 1
        fi
    fi
    "${PYTHON_BIN:-python3}" - "$rawf" "$runs" <<'PY'
import math
import re
import statistics
import sys
with open(sys.argv[1], encoding="utf-8", errors="replace") as handle:
    raw = handle.read()
values = [float(v) for v in re.findall(r"Run Time[^\n]*?\breal\s+([0-9.eE+-]+)", raw)]
if len(values) != int(sys.argv[2]) or not all(math.isfinite(v) and v > 0 for v in values):
    print("NA 0")
    sys.exit(1)
print(f"{statistics.median(values):.9f} {len(values)}")
PY
}

# Parse the already-collected profiles; never execute another query.
# DuckDB supplies optimizer totals; the ON total also includes the otherwise
# untracked OuterYan cost-model phase. The decision trace supplies non-overlapping
# workflow phases (simplification, desimplification, join reorder, and so on).
# Generic DuckDB per-pass timings are intentionally not exported.
# Echoes a pipe-delimited record:
#   off_total|on_total|delta|on_over_off|off_phase_sum|on_phase_sum|
#   off_other|on_other|samples|off_phases_json|on_phases_json|
#   comparable_delta_json|outeryan_focus
oy_optimizer_profile_from_files() {
    local profiledir="$1" query="$2"
    local rawf="$profiledir/optimizer_duckdb.log" duck_rc=0
    local tracef="$profiledir/optimizer_outeryan.trace"
    "${PYTHON_BIN:-python3}" - "$rawf" "$profiledir" "${query%;}" "$duck_rc" "$tracef" <<'PY' \
        || return $?
import json
import math
import os
import sys

raw_path, profile_dir, expected_query, duck_rc_text, trace_path = sys.argv[1:]
failure = "|".join(["NA"] * 13)


def normalize_query(value):
    lines = value.strip().splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
        lines.pop(0)
    return " ".join("\n".join(lines).strip().rstrip(";").split())


def seconds(value, label):
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"invalid {label} value {value!r}")
    return parsed


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


try:
    with open(raw_path, encoding="utf-8", errors="replace") as handle:
        raw = handle.read()
    if int(duck_rc_text) != 0:
        errors = [line.strip() for line in raw.splitlines() if "Error:" in line]
        detail = f": {errors[-1]}" if errors else ""
        raise ValueError(f"duckdb exited with status {duck_rc_text}{detail}")
    if "Error:" in raw:
        raise ValueError("duckdb reported an error")

    expected = normalize_query(expected_query)
    selected = {}
    for mode in ("duckdb", "outeryan"):
        path = os.path.join(profile_dir, f"optimizer_{mode}_1.json")
        with open(path, encoding="utf-8") as handle:
            root = json.load(handle)
        missing = sorted({"query_name", "all_optimizers"}.difference(root))
        if missing:
            raise ValueError(f"optimizer profile {mode} is missing keys: {', '.join(missing)}")
        if normalize_query(root["query_name"]) != expected:
            raise ValueError(f"optimizer profile {mode} query_name does not match")
        total = seconds(root["all_optimizers"], "all_optimizers")
        if total <= 0:
            raise ValueError(f"optimizer profile {mode} has non-positive total")
        selected[mode] = (total, root)

    off_total, off_root = selected["duckdb"]
    on_all_optimizers, _ = selected["outeryan"]
    off_phases = {
        "duckdb_simplification": seconds(
            off_root.get("optimizer_outer_join_simplification", 0.0),
            "optimizer_outer_join_simplification",
        ),
        "duckdb_join_reorder": seconds(
            off_root.get("optimizer_join_order", 0.0), "optimizer_join_order"
        ),
    }

    with open(trace_path, encoding="utf-8", errors="replace") as handle:
        decisions = [line.strip() for line in handle if line.startswith("[OY_DECISION]")]
    if not decisions:
        raise ValueError("ON execution emitted no OuterYan decision record")
    fields = {}
    for token in decisions[-1].split()[1:]:
        if "=" in token:
            key, value = token.split("=", 1)
            fields[key] = value
    phase_names = (
        "applicability", "build_ot", "simplification", "semijoin_pair_planning",
        "desimplification", "outeryan_join_reorder", "duckdb_simplification",
        "duckdb_join_reorder", "cost_model", "resimplification",
        "aggregate_pushdown_marking", "plan_lowering", "semijoin_insertion",
        "aggregate_pushdown",
    )
    on_phases = {}
    for name in phase_names:
        key = f"phase_{name}_s"
        if fields.get(key) in (None, "NA"):
            continue
        on_phases[name] = seconds(fields[key], key)

    # DuckDB's `all_optimizers` is the sum of named RunOptimizer phases. The
    # OuterYan cost comparison deliberately sits between those named phases, so
    # DuckDB does not include it. Add that one uncovered, non-overlapping phase
    # to the ON total; every other custom workflow phase is already inside a
    # named optimizer timer.
    on_total = on_all_optimizers + on_phases.get("cost_model", 0.0)
    off_phase_sum = sum(off_phases.values())
    on_phase_sum = sum(on_phases.values())
    tolerance = max(1e-9, on_total * 0.02)
    if on_phase_sum > on_total + tolerance:
        raise ValueError(
            f"OuterYan workflow phases {on_phase_sum:.9f}s exceed adjusted optimizer total {on_total:.9f}s"
        )
    off_other = max(0.0, off_total - off_phase_sum)
    on_other = max(0.0, on_total - on_phase_sum)
    off_phases["other_optimizer"] = off_other
    on_phases["other_optimizer"] = on_other
    deltas = {
        "optimizer_total": on_total - off_total,
        "duckdb_simplification": on_phases.get("duckdb_simplification", 0.0)
        - off_phases.get("duckdb_simplification", 0.0),
        "duckdb_join_reorder": on_phases.get("duckdb_join_reorder", 0.0)
        - off_phases.get("duckdb_join_reorder", 0.0),
    }
    focus_names = (
        "simplification", "desimplification", "outeryan_join_reorder",
        "resimplification", "aggregate_pushdown",
    )
    focus = ",".join(f"{name}={on_phases.get(name, 0.0):.9f}" for name in focus_names)
    values = (
        f"{off_total:.9f}",
        f"{on_total:.9f}",
        f"{on_total - off_total:.9f}",
        f"{on_total / off_total:.9f}",
        f"{off_phase_sum:.9f}",
        f"{on_phase_sum:.9f}",
        f"{off_other:.9f}",
        f"{on_other:.9f}",
        "1",
        compact(off_phases),
        compact(on_phases),
        compact(deltas),
        focus,
    )
    print("|".join(values))
except Exception as exc:
    print(f"OPTIMIZER-PROFILE-ERROR: {exc}", file=sys.stderr)
    print(failure)
    sys.exit(1)
PY
}

oy_optimizer_profile_failure() {
    local separator="" field
    for field in {1..13}; do
        printf '%sNA' "$separator"
        separator='|'
    done
    printf '\n'
}
