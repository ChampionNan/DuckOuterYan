#!/usr/bin/env bash
# Sourced by experiment_onoff.sh; uses its tracked oy_duck and timeout helpers.
# Separate native ON profiling: one warm-up plus N samples at the timing thread
# count. This does not contribute to the unprofiled OFF/ON timing medians.
# The optional ninth argument retains raw profiles and the CLI log for auditing.
# Parser restored from the validated multi-thread profiler in 6ff227865e.
# Total-Time is DuckDB's high-resolution root query latency; CPU-Time is the
# recursive sum of native OPERATOR_TIMING across all workers. R1/R2 sum the
# corresponding SJ build/probe operator work and R3 sums join-operator work.
# The complete tuple belonging to the median Total-Time sample is selected, so
# all values come from one execution. OtherCPU is the exact CPU-Time residual.
# These are aggregate active operator work-seconds, not contiguous phase wall
# times; parallel operator work can exceed Total-Time.
# Echoes: "round1_s round2_s real_join_s total_time_s cpu_time_s r1_ratio
# r2_ratio sj_ratio real_join_ratio other_s other_ratio round1_operator_count
# round2_operator_count real_join_operator_count timed_sample_count"
# (fifteen NA values on failure).
oy_phase_profile() {
    local db="$1" query="$2" threads="$3" runs="$4" expected_plan="$5"
    local expected_r1_pairs="$6" expected_r2_pairs="$7" proven_empty="$8"
    local profile_dest="${9:-}"
    local sqlf rawf profiledir profilef profile_sql i profile_rc=0
    sqlf=$(mktemp) || { oy_phase_profile_failure; return 1; }
    rawf=$(mktemp) || { rm -f "$sqlf"; oy_phase_profile_failure; return 1; }
    if [ -n "$profile_dest" ]; then
        profiledir="$profile_dest"
        [ -d "$profiledir" ] || { rm -f "$sqlf" "$rawf"; oy_phase_profile_failure; return 1; }
    else
        profiledir=$(mktemp -d "$OY_RUN_TMPDIR/oy_profile.XXXXXX") || {
            rm -f "$sqlf" "$rawf"
            oy_phase_profile_failure
            return 1
        }
    fi
    printf ".timer off\n.mode trash\nCALL disable_profiling();\nPRAGMA threads=%s;\n%s\n%s\n" \
        "$threads" "$(oy_statement_timeout_sql "$OY_TIMEOUT_SECS")" "$OY_ON" > "$sqlf"
    # Index 0 is the warm-up. It is profiled too, so warm-up and timed samples
    # have the same instrumentation and result-consumption behavior.
    for ((i=0; i<=runs; i++)); do
        profilef="$profiledir/profile_${i}.json"
        profile_sql="${profilef//"'"/"''"}"
        printf "CALL enable_profiling(format='json', save_location='%s', coverage='select', mode='standard', metrics=['QUERY_NAME','LATENCY','CPU_TIME','OPERATOR_NAME','OPERATOR_TYPE','OPERATOR_TIMING']);\n%s;\nCALL disable_profiling();\n" \
            "$profile_sql" "${query%;}" >> "$sqlf"
    done

    # The SQL statement timeout remains per execution; only the external
    # process watchdog is scaled for warm-up + timed samples.
    local saved_to="$OY_TIMEOUT_SECS" duck_rc=0
    [ -n "$OY_TIMEOUT_BIN" ] && [ "$OY_TIMEOUT_SECS" != "0" ] \
        && OY_TIMEOUT_SECS=$(( OY_TIMEOUT_SECS * (runs + 1) + OY_BATCH_GRACE_SECS ))
    if oy_duck "$db" -noheader < "$sqlf" > "$rawf" 2>&1; then
        duck_rc=0
    else
        duck_rc=$?
    fi
    OY_TIMEOUT_SECS="$saved_to"

    "${PYTHON_BIN:-python3}" - "$rawf" "$profiledir" "$runs" "${query%;}" "$duck_rc" \
        "$expected_plan" "$expected_r1_pairs" "$expected_r2_pairs" "$proven_empty" <<'PY' || profile_rc=$?
import json
import math
import os
import sys

(
    raw_path,
    profile_dir,
    runs_text,
    expected_query,
    duck_rc_text,
    expected_plan,
    expected_r1_pairs_text,
    expected_r2_pairs_text,
    proven_empty_text,
) = sys.argv[1:]
runs = int(runs_text)
failure = "NA " * 14 + "NA"

def normalize_query(value):
    # DuckDB's QUERY_NAME metric omits leading SQL comments. Generated core
    # queries carry provenance comments, so remove only the leading comment
    # block before comparing the profiled statement with the requested query.
    lines = value.strip().splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
        lines.pop(0)
    return " ".join("\n".join(lines).strip().rstrip(";").split())

try:
    with open(raw_path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    if int(duck_rc_text) != 0:
        error_lines = [line.strip() for line in raw.splitlines() if "Error:" in line]
        detail = f": {error_lines[-1]}" if error_lines else ""
        raise ValueError(f"duckdb exited with status {duck_rc_text}{detail}")
    if "Error:" in raw:
        raise ValueError("duckdb reported an error")

    if expected_plan not in ("DUCKDB", "OUTERYAN"):
        raise ValueError(f"unknown selected plan {expected_plan!r}")
    if proven_empty_text not in ("0", "1"):
        raise ValueError(f"invalid proven-empty flag {proven_empty_text!r}")
    proven_empty = proven_empty_text == "1"

    def expected_pairs(value, label):
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid {label} planned pair count {value!r}") from exc
        if parsed < 0:
            raise ValueError(f"negative {label} planned pair count")
        return parsed

    expected_round_pairs = (0, 0)
    if expected_plan == "OUTERYAN":
        expected_round_pairs = (
            expected_pairs(expected_r1_pairs_text, "R1"),
            expected_pairs(expected_r2_pairs_text, "R2"),
        )
    join_operator_types = {
        "BLOCKWISE_NL_JOIN",
        "NESTED_LOOP_JOIN",
        "HASH_JOIN",
        "CROSS_PRODUCT",
        "PIECEWISE_MERGE_JOIN",
        "IE_JOIN",
        "LEFT_DELIM_JOIN",
        "RIGHT_DELIM_JOIN",
        "POSITIONAL_JOIN",
        "ASOF_JOIN",
    }
    round1_operator_names = {"SJ_BUILD_ROUND_1", "SJ_PROBE_ROUND_1"}
    round2_operator_names = {"SJ_BUILD_ROUND_2", "SJ_PROBE_ROUND_2"}

    def seconds_to_ns(value, label):
        value = float(value)
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"invalid {label} value {value!r}")
        return int(round(value * 1_000_000_000))

    def operator_components(root, profile_index):
        totals_ns = [0, 0, 0]
        operator_counts = [0, 0, 0]

        def visit(node):
            if not isinstance(node, dict):
                raise ValueError(f"profile {profile_index} contains a non-object operator node")
            name = node.get("operator_name")
            operator_type = node.get("operator_type")
            if not isinstance(name, str) or not isinstance(operator_type, str):
                raise ValueError(f"profile {profile_index} operator identity is missing")
            if "operator_timing" not in node:
                raise ValueError(f"profile {profile_index} operator {name!r} has no timing")
            elapsed_ns = seconds_to_ns(
                node["operator_timing"], f"operator_timing for {name!r}"
            )

            phase = None
            if name in round1_operator_names:
                phase = 0
            elif name in round2_operator_names:
                phase = 1
            elif operator_type in join_operator_types:
                phase = 2
            if phase is not None:
                totals_ns[phase] += elapsed_ns
                operator_counts[phase] += 1

            children = node.get("children", [])
            if not isinstance(children, list):
                raise ValueError(f"profile {profile_index} operator {name!r} has invalid children")
            for child in children:
                visit(child)

        children = root.get("children")
        if not isinstance(children, list):
            raise ValueError(f"profile {profile_index} has no physical-operator tree")
        for child in children:
            visit(child)
        return totals_ns, operator_counts

    samples = []
    expected = normalize_query(expected_query)
    for index in range(0, runs + 1):
        path = os.path.join(profile_dir, f"profile_{index}.json")
        with open(path, encoding="utf-8") as f:
            root = json.load(f)
        missing = sorted({"query_name", "latency", "cpu_time", "children"}.difference(root))
        if missing:
            raise ValueError(f"profile {index} is missing keys: {', '.join(missing)}")
        if normalize_query(root["query_name"]) != expected:
            raise ValueError(f"profile {index} query_name does not match the timed query")

        profile_wall_ns = seconds_to_ns(root["latency"], "latency")
        if profile_wall_ns <= 0:
            raise ValueError(f"profile {index} has non-positive latency")
        profile_cpu_ns = seconds_to_ns(root["cpu_time"], "cpu_time")
        if profile_cpu_ns <= 0:
            raise ValueError(f"profile {index} has non-positive cpu_time")

        totals_ns, operator_counts = operator_components(root, index)

        if expected_plan == "DUCKDB" and any(totals_ns[:2] + operator_counts[:2]):
            raise ValueError(f"profile {index} DuckDB plan unexpectedly executed a semi-join phase")
        if not proven_empty and operator_counts[2] == 0:
            raise ValueError(f"profile {index} non-empty join plan has no R3 operator")
        if expected_plan == "OUTERYAN" and not proven_empty:
            for phase, pairs, elapsed_ns, operators in zip(
                ("R1", "R2"), expected_round_pairs, totals_ns[:2], operator_counts[:2]
            ):
                if pairs == 0 and (elapsed_ns != 0 or operators != 0):
                    raise ValueError(f"profile {index} {phase} ran with zero planned pairs")
                if pairs > 0 and operators == 0:
                    raise ValueError(f"profile {index} {phase} has {pairs} planned pairs but did not run")

        component_total_ns = sum(totals_ns)
        if component_total_ns > profile_cpu_ns:
            # Root CPU_TIME is rounded once, while each classified operator is
            # rounded independently. Accept only the maximum possible
            # nanosecond conversion delta, then normalize CPU-Time upward so
            # the displayed integer-nanosecond closure remains exact.
            rounding_tolerance_ns = max(1, sum(operator_counts) + 1)
            if component_total_ns - profile_cpu_ns > rounding_tolerance_ns:
                raise ValueError(
                    f"profile {index} components {component_total_ns}ns exceed "
                    f"CPU-Time {profile_cpu_ns}ns"
                )
            profile_cpu_ns = component_total_ns
        other_ns = profile_cpu_ns - component_total_ns

        # Profile 0 is the warm-up. It receives every consistency check above,
        # but is not included in the timed median.
        if index == 0:
            continue
        samples.append(
            (profile_wall_ns, index, profile_cpu_ns, *totals_ns, other_ns, *operator_counts)
        )

    if not samples:
        raise ValueError("no complete timed profile samples")
    samples.sort(key=lambda sample: (sample[0], sample[1]))
    wall_ns, _, cpu_ns, r1_ns, r2_ns, real_join_ns, other_ns, r1_operators, r2_operators, real_join_operators = \
        samples[(len(samples) - 1) // 2]

    def seconds(value_ns):
        return f"{value_ns / 1_000_000_000:.9f}"

    # Quantize the three classified CPU-work shares downward and give the
    # remaining units to OtherCPU. The four displayed ratios therefore add to
    # exactly 1.000000000 while each remains in [0, 1].
    ratio_scale = 1_000_000_000
    r1_ratio_units = r1_ns * ratio_scale // cpu_ns
    r2_ratio_units = r2_ns * ratio_scale // cpu_ns
    join_ratio_units = real_join_ns * ratio_scale // cpu_ns
    other_ratio_units = ratio_scale - r1_ratio_units - r2_ratio_units - join_ratio_units

    def ratio(units):
        return f"{units // ratio_scale}.{units % ratio_scale:09d}"

    print("{} {} {} {} {} {} {} {} {} {} {} {} {} {} {}".format(
        seconds(r1_ns), seconds(r2_ns), seconds(real_join_ns), seconds(wall_ns), seconds(cpu_ns),
        ratio(r1_ratio_units), ratio(r2_ratio_units), ratio(r1_ratio_units + r2_ratio_units),
        ratio(join_ratio_units), seconds(other_ns), ratio(other_ratio_units), r1_operators, r2_operators,
        real_join_operators, len(samples)))
except Exception as exc:
    print(f"PROFILE-ERROR: {exc}", file=sys.stderr)
    print(failure)
    sys.exit(1)
PY
    if [ -n "$profile_dest" ]; then
        cp "$rawf" "$profiledir/duckdb.log"
    else
        for ((i=0; i<=runs; i++)); do
            rm -f "$profiledir/profile_${i}.json"
        done
        rmdir "$profiledir" 2>/dev/null || true
    fi
    rm -f "$sqlf" "$rawf"
    return "$profile_rc"
}

oy_phase_profile_failure() {
    echo "NA NA NA NA NA NA NA NA NA NA NA NA NA NA NA"
}
