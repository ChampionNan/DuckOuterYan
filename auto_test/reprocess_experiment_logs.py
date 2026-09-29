#!/usr/bin/env python3
"""Recover per-corpus CSVs and statistics from saved result logs, without running SQL."""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import math
from pathlib import Path
import re
import sys


FILE_PATTERN = re.compile(r"^(.*?_(\d{8}_\d{6})(?:_t\d+)?)(?:_(v[123])(_selectivity_stress)?)?\.txt$")
QUERY_PATTERN = re.compile(r"^\[\s*(\d+)/(\d+)\]\s+query=(\S+)\s*$", re.MULTILINE)
MISSING = {"", "NA", "-", "NAs"}
CSV_COLUMNS = """
experiment_group corpus_version corpus_revision corpus_scope workload_category query_class
query family sql_path relation_count aggregate_query aggregate_pushdown_applied reorder outer_reordered
cost_gate_applied outer_yan_selected selected_plan baseline_proven_empty decision_reason formula_id
selection_mode raw_cost_winner gate_result default_filter_upper_bound_checked default_filter_upper_bound_selected
full_reduction_cardinality_lower_bound_applied uncertain_filter_amplification_guard stretch_cost_gate_eligible
stretch_cost_gate_selected unary_filter_selectivity low_selectivity_cost_gate_eligible low_selectivity_cost_gate_selected
low_selectivity_cost_ratio_limit baseline_join_input_rows candidate_join_input_rows candidate_to_baseline_join_input_ratio
semijoin_retained_cardinality_ratio uncertain_filter_cardinality_amplification baseline_cost candidate_join_cost
semijoin_raw_cost semijoin_cost_ratio weighted_semijoin_cost candidate_total cost_ratio_limit baseline_threshold
round1_build round1_probe round2_build round2_probe round1_pairs round1_filters round2_pairs round2_filters
raw_cost_delta raw_cost_ratio gate_lhs gate_rhs gate_margin inner_output_weight unmatched_left_weight unmatched_right_weight
semijoin_materialize_weight semijoin_filter_build_weight semijoin_replay_weight semijoin_probe_lookup_weight
semijoin_probe_emit_weight kernel kernel_detail kernel_hash_reasons correct note timing_status timing_threads tm_off tm_on
tm_speedup optimizer_profile_status optimizer_timed_samples optimizer_duckdb_total_s optimizer_outeryan_total_s
optimizer_overhead_s optimizer_outeryan_to_duckdb_ratio optimizer_duckdb_measured_phase_s optimizer_outeryan_measured_phase_s
optimizer_duckdb_other_s optimizer_outeryan_other_s optimizer_duckdb_phases_json optimizer_outeryan_phases_json
optimizer_phase_delta_json optimizer_profile_directory rows effective_pass duckdb_plan enabled_plan trace_file cost_file
profile_status profile_threads profile_round1_operator_s profile_round2_operator_s profile_round3_operator_s
profile_round1_operator_count profile_round2_operator_count profile_round3_operator_count profile_wall_time_s
profile_total_time_s profile_cpu_time_s profile_round1_ratio profile_round2_ratio profile_total_sj_ratio
profile_round3_ratio profile_other_elapsed_s profile_other_ratio profile_timed_samples profile_directory
""".split()


def pairs(text):
    return dict(re.findall(r"\b([A-Za-z_][A-Za-z_0-9]*)=([^\s;\]]+)", text))


def section(text, name):
    match = re.search(r"\b" + re.escape(name) + r"=\[([^\]]*)\]", text)
    return match.group(1) if match else ""


def mapped(row, text, mapping):
    fields = pairs(text)
    for source, target in mapping.items():
        if source in fields:
            row[target] = fields[source]


def normalize_timeout(row):
    if "TIMEOUT" in row.get("note", "").upper():
        row["correct"] = "TIMEOUT"


def parse_record(query, result, context, decision):
    row = {"query": query}
    mapped(row, result.split("runtime_s=[", 1)[0], {
        "correct": "correct", "timing": "timing_status", "aggregate": "aggregate_query",
        "aggregate_pushdown": "aggregate_pushdown_applied", "reorder": "outer_reordered",
        "selected": "selected_plan", "kernel": "kernel_detail", "threads": "timing_threads",
    })
    row["reorder"] = "Yes" if row.get("outer_reordered") == "1" else "No"
    row["kernel"] = row.get("kernel_detail", "").split("(", 1)[0]
    mapped(row, section(result, "runtime_s"), {"DuckDB": "tm_off", "OuterYan": "tm_on"})
    mapped(row, result, {"speedup": "tm_speedup"})
    mapped(row, section(result, "optimization_s"), {
        "status": "optimizer_profile_status", "DuckDB": "optimizer_duckdb_total_s",
        "OuterYan": "optimizer_outeryan_total_s", "overhead": "optimizer_overhead_s",
        "ratio": "optimizer_outeryan_to_duckdb_ratio", "samples": "optimizer_timed_samples",
    })
    mapped(row, context.split("breakdown_s=[", 1)[0], {
        "family": "family", "category": "workload_category", "nrel": "relation_count",
        "pass": "effective_pass", "note": "note", "rows": "rows", "sql": "sql_path",
    })
    mapped(row, section(context, "breakdown_s"), {
        "status": "profile_status", "CPU": "profile_cpu_time_s", "R1": "profile_round1_operator_s",
        "R2": "profile_round2_operator_s", "R3": "profile_round3_operator_s",
        "Other": "profile_other_elapsed_s", "wall": "profile_wall_time_s", "samples": "profile_timed_samples",
    })
    row["profile_total_time_s"] = row.get("profile_cpu_time_s", "NA")
    mapped(row, section(decision, "plan"), {
        "mode": "selection_mode", "reason": "decision_reason", "raw_winner": "raw_cost_winner",
        "gate": "gate_result", "gate_applied": "cost_gate_applied", "proven_empty": "baseline_proven_empty",
        "outer_yan_selected": "outer_yan_selected", "formula": "formula_id",
    })
    mapped(row, section(decision, "risk"), {
        "default_filter_upper_checked": "default_filter_upper_bound_checked",
        "selected": "default_filter_upper_bound_selected", "retained": "semijoin_retained_cardinality_ratio",
        "amplification": "uncertain_filter_cardinality_amplification", "guard": "uncertain_filter_amplification_guard",
        "full_reduction_bound": "full_reduction_cardinality_lower_bound_applied",
        "stretch_eligible": "stretch_cost_gate_eligible", "stretch_selected": "stretch_cost_gate_selected",
        "unary_selectivity": "unary_filter_selectivity", "low_selectivity_eligible": "low_selectivity_cost_gate_eligible",
        "low_selectivity_selected": "low_selectivity_cost_gate_selected",
        "low_selectivity_limit": "low_selectivity_cost_ratio_limit", "join_input_ratio": "candidate_to_baseline_join_input_ratio",
    })
    cost = section(decision, "cost")
    match = re.search(r"OuterYan=(\S+) \+ (\S+)\*(\S+) = ([^;]+);", cost)
    if match:
        row.update(zip(("candidate_join_cost", "semijoin_cost_ratio", "semijoin_raw_cost", "candidate_total"), match.groups()))
    mapped(row, cost, {"DuckDB": "baseline_cost", "delta": "raw_cost_delta", "raw_ratio": "raw_cost_ratio"})
    gate = section(decision, "gate_cmp")
    match = re.search(r"numeric:(\S+) <= (\S+) \(= ([^*]+)\*", gate)
    if match:
        row.update(zip(("gate_lhs", "gate_rhs", "cost_ratio_limit"), match.groups()))
        row["baseline_threshold"] = row["gate_rhs"]
    mapped(row, gate, {"margin": "gate_margin"})
    sj = section(decision, "SJ")
    for number in (1, 2):
        match = re.search(r"R" + str(number) + r"\(([^)]*)\)", sj)
        if match:
            mapped(row, match.group(1), {key: f"round{number}_{key}" for key in ("build", "probe", "pairs", "filters")})
    mapped(row, sj, {"weighted": "weighted_semijoin_cost"})
    weights = section(decision, "weights")
    for name, mapping in (
        ("join", {"inner": "inner_output_weight", "unmatched_left": "unmatched_left_weight", "unmatched_right": "unmatched_right_weight"}),
        ("SJ", {"materialize": "semijoin_materialize_weight", "filter_build": "semijoin_filter_build_weight",
                "replay": "semijoin_replay_weight", "lookup": "semijoin_probe_lookup_weight", "emit": "semijoin_probe_emit_weight"}),
    ):
        match = re.search(r"\b" + name + r"\(([^)]*)\)", weights)
        if match:
            mapped(row, match.group(1), mapping)
    # TXT omits full optimizer phase maps, operator counts and input cardinalities.
    # Leave them unavailable; a sibling CSV supplies the original values if present.
    normalize_timeout(row)
    return row


def read_log(path):
    match = FILE_PATTERN.match(path.name)
    if not match:
        raise ValueError(f"Unsupported result filename: {path}")
    prefix, timestamp, version, stress = match.groups()
    text = re.sub(r"\x1b\[[0-9;]*m", "", path.read_text(encoding="utf-8"))
    headers = list(QUERY_PATTERN.finditer(text))
    if not headers:
        raise ValueError(f"No query result blocks: {path}")
    expected = {int(header.group(2)) for header in headers}
    if len(expected) != 1:
        raise ValueError(f"Mixed corpus sizes in {path}")
    records = []
    incomplete = []
    for index, header in enumerate(headers):
        body = text[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(text)]
        parts = [re.search(r"^\s*" + key + r": (.*)$", body, re.MULTILINE)
                 for key in ("result", "context", "decision")]
        if not all(parts):
            incomplete.append(header.group(3))
            continue
        row = parse_record(header.group(3), *(part.group(1) for part in parts))
        if not row.get("family"):
            raise ValueError(f"Missing family for {row['query']} in {path}")
        records.append(row)
    class_match = re.search(r"^# class\s*:.*\bquery_class=(\S+)", text, re.MULTILINE)
    category = "v3_selectivity_stress" if stress else "v3_aggregation" if version == "v3" else version or "all"
    revision = re.search(r"^# corpus\s*:.*\brevision=([^,\s]+)", text, re.MULTILINE)
    scope = re.search(r"^# corpus\s*:.*\bscope=([^,\s]+)", text, re.MULTILINE)
    if not version:
        for row in records:
            row["query_class"] = row.get("workload_category") or row["query"].split("__", 1)[0]
    metadata = {
        "experiment_group": timestamp, "corpus_version": version or "",
        "corpus_revision": revision.group(1) if revision else "",
        "corpus_scope": scope.group(1) if scope else "selectivity-stress" if stress else "benchmark",
        "workload_category": category,
        "query_class": class_match.group(1) if class_match else "",
    }
    return prefix, metadata, records, expected.pop(), incomplete


def identity(row):
    return row["family"], row["query"]


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        if not reader.fieldnames or not {"family", "query"}.issubset(reader.fieldnames):
            raise ValueError(f"Missing query identity columns: {path}")
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"Truncated or malformed CSV: {path}")
    if len({identity(row) for row in rows}) != len(rows):
        raise ValueError(f"Duplicate query identities: {path}")
    return rows, reader.fieldnames


def check_existing(logged, existing, path):
    for key in ("selected_plan", "correct", "timing_threads", "tm_off", "tm_on"):
        left, right = logged.get(key, ""), existing.get(key, "")
        if left in MISSING and right in MISSING:
            continue
        if key in ("tm_off", "tm_on"):
            try:
                if math.isclose(float(left), float(right), rel_tol=1e-8, abs_tol=1e-9):
                    continue
            except ValueError:
                pass
        if left.upper() != right.upper():
            raise ValueError(f"TXT/CSV mismatch for {logged['query']} {key} in {path}: {left!r} vs {right!r}")


def recover(path, output_dir):
    prefix, metadata, logged_rows, expected, incomplete = read_log(path)
    if len({identity(row) for row in logged_rows}) != len(logged_rows):
        raise ValueError(f"Duplicate query identities in {path}")
    sibling = path.with_suffix(".csv")
    existing, columns = read_csv(sibling) if sibling.exists() else ([], CSV_COLUMNS)
    existing_by_id = {identity(row): row for row in existing}
    groups = {row.get("experiment_group", "") for row in existing} - {""}
    if len(groups) > 1:
        raise ValueError(f"Multiple experiment groups in {sibling}")
    if groups:
        metadata["experiment_group"] = groups.pop()
    rows = []
    recovered = 0
    for row in logged_rows:
        original = existing_by_id.pop(identity(row), None)
        if original is not None:
            original = dict(original)
            normalize_timeout(original)
            check_existing(row, original, path)
            # Preserve unrounded CSV timings, full phase JSON, and unavailable fields.
            row = {**row, **original}
        else:
            recovered += 1
        rows.append({**metadata, **row})
    for row in existing_by_id.values():
        normalize_timeout(row)
        rows.append({**metadata, **row})
    if len(rows) > expected:
        raise ValueError(f"More result rows than the declared corpus size in {path}")
    if not rows:
        raise ValueError(f"No complete results to recover from {path}")
    target = output_dir / sibling.name
    if target.resolve() == sibling.resolve():
        raise ValueError("Use a separate --output-dir to preserve original results")
    # The harness schema stays consistent even when a sibling CSV is missing.
    fields = list(dict.fromkeys(CSV_COLUMNS + columns + [key for row in rows for key in row]))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields, restval="NA")
        writer.writeheader()
        writer.writerows(rows)
    info = {
        "source_log": str(path.resolve()), "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_csv": str(sibling.resolve()) if sibling.exists() else None,
        "source_csv_sha256": hashlib.sha256(sibling.read_bytes()).hexdigest() if sibling.exists() else None,
        "output_csv": str(target.resolve()), "expected_queries": expected, "recovered_queries": len(rows),
        "complete": len(rows) == expected, "incomplete_log_blocks": incomplete,
        "txt_only_rows": recovered, "experiment_group": metadata["experiment_group"],
        "workload_category": metadata["workload_category"],
    }
    return prefix, target, info


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", help="Result TXT paths or quoted glob patterns; historical versioned logs are supported")
    parser.add_argument("--output-dir", required=True, type=Path, help="Separate directory; originals are never overwritten")
    parser.add_argument("--csv-only", action="store_true", help="Recover CSVs using only the Python standard library")
    args = parser.parse_args(argv)
    paths = set()
    for pattern in args.logs:
        matches = glob.glob(pattern)
        if not matches:
            parser.error(f"No result logs match {pattern}")
        paths.update(Path(match).resolve() for match in matches)
    groups = {}
    infos = []
    for path in sorted(paths):
        prefix, target, info = recover(path, args.output_dir)
        groups.setdefault(prefix, []).append((target, info))
        infos.append(info)
        state = "complete" if info["complete"] else "INCOMPLETE"
        print(f"{target.name}: {info['recovered_queries']}/{info['expected_queries']} ({state}); "
              f"{info['txt_only_rows']} TXT-only rows", flush=True)
    manifest = {"method": "saved TXT/CSV only; no queries executed", "files": infos, "groups": []}
    errors = []
    for prefix, entries in groups.items():
        categories = {info["workload_category"] for _, info in entries}
        missing = (sorted({"v1", "v2", "v3_aggregation", "v3_selectivity_stress"} - categories)
                   if categories & {"v1", "v2", "v3_aggregation", "v3_selectivity_stress"} else [])
        info = {"prefix": prefix, "missing_categories": missing, "statistics": "not-requested"}
        if missing:
            print(f"{prefix}: unavailable categories: {', '.join(missing)}", file=sys.stderr)
        if not args.csv_only:
            try:
                if __package__:
                    from .gen_experiment_result import statistics_main
                else:
                    from gen_experiment_result import statistics_main
                run_ids = {entry["experiment_group"] for _, entry in entries}
                if len(run_ids) != 1:
                    raise ValueError("Mixed experiment groups; supply the original sibling CSVs for all logs")
                statistics_main([
                    "--output-dir", str(args.output_dir / (prefix + "_statistics")),
                    "--combined-csv", str(args.output_dir / (prefix + "_all.csv")),
                    "--run", run_ids.pop(), *(str(path) for path, _ in entries),
                ])
                info["statistics"] = "written"
            except (ImportError, ValueError, OSError, AttributeError) as error:
                info["statistics"] = "failed"
                info["error"] = str(error)
                errors.append(f"{prefix}: {error}")
        manifest["groups"].append(info)
    (args.output_dir / "recovery_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
