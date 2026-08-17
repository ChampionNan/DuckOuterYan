#!/usr/bin/env python3
"""Audit OuterYan's cost gate with forced execution of changed candidates.

The normal experiment determines whether OuterYan produced a genuinely
different base-relation grouping.  A second experiment, run with
DUCKDB_OY_FORCE_CANDIDATE=1, measures those candidates even when the normal
cost gate rejected them.  This script joins both CSVs and classifies the gate
independently for the single-thread and multi-thread measurements.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


KEY_COLUMNS = ("family", "sql_path", "effective_pass")
REQUIRED_NORMAL_COLUMNS = {
    "query",
    "family",
    "sql_path",
    "outer_reordered",
    "outer_yan_selected",
    "selected_plan",
    "decision_reason",
    "selection_mode",
    "cost_gate_applied",
    "gate_result",
    "correct",
    "note",
    "rows",
    "effective_pass",
    "formula_id",
    "relation_count",
    "baseline_proven_empty",
    "baseline_cost",
    "candidate_join_cost",
    "semijoin_raw_cost",
    "semijoin_cost_ratio",
    "candidate_total",
    "raw_cost_ratio",
    "candidate_to_baseline_join_input_ratio",
    "inner_output_weight",
    "unmatched_left_weight",
    "unmatched_right_weight",
    "semijoin_materialize_weight",
    "semijoin_filter_build_weight",
    "semijoin_replay_weight",
    "semijoin_probe_lookup_weight",
    "semijoin_probe_emit_weight",
}
REQUIRED_FORCED_COLUMNS = REQUIRED_NORMAL_COLUMNS | {
    "correct",
    "note",
    "selection_mode",
    "tm_speedup",
    "t1_speedup",
    "tm_off",
    "tm_on",
    "t1_off",
    "t1_on",
}

PARAMETER_COLUMNS = (
    "semijoin_cost_ratio",
    "inner_output_weight",
    "unmatched_left_weight",
    "unmatched_right_weight",
    "semijoin_materialize_weight",
    "semijoin_filter_build_weight",
    "semijoin_replay_weight",
    "semijoin_probe_lookup_weight",
    "semijoin_probe_emit_weight",
)

COST_COLUMNS = (
    "baseline_cost",
    "candidate_join_cost",
    "semijoin_raw_cost",
    "candidate_total",
    "raw_cost_ratio",
    "candidate_to_baseline_join_input_ratio",
)

SELECT_REASONS = {"COST_OUTERYAN_BETTER", "COST_OUTERYAN_STRETCH"}
REJECT_REASONS = {
    "COST_DUCKDB_BETTER",
    "COST_UNCERTAIN_FILTER_AMPLIFICATION",
    "COST_UNAVAILABLE",
}

OUTPUT_COLUMNS = (
    "query",
    "family",
    "sql_path",
    "effective_pass",
    "normal_decision",
    "normal_selected_plan",
    "normal_outer_yan_selected",
    "forced_decision",
    "forced_selected_plan",
    "forced_correct",
    "forced_note",
    "forced_reported_tm_speedup",
    "forced_reported_t1_speedup",
    "normal_gate_valid",
    "forced_reorder_match",
    "query_match",
    "formula_match",
    "relation_count_match",
    "parameters_match",
    "costs_match",
    "result_rows_match",
    "baseline_cost",
    "candidate_join_cost",
    "semijoin_raw_cost",
    "candidate_total",
    "raw_cost_ratio",
    "candidate_to_baseline_join_input_ratio",
    "tm_off",
    "tm_on",
    "tm_speedup",
    "tm_outcome",
    "tm_gate_judgment",
    "t1_off",
    "t1_on",
    "t1_speedup",
    "t1_outcome",
    "t1_gate_judgment",
    "consensus",
    "comparable",
    "primary_metric",
    "primary_gate_judgment",
    "audit_note",
)


def load_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        missing = sorted(required - columns)
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(missing)}")
        return list(reader)


def row_key(row: dict[str, str]) -> tuple[str, str, str]:
    return tuple(row[column] for column in KEY_COLUMNS)  # type: ignore[return-value]


def index_rows(
    rows: Iterable[dict[str, str]], source: Path
) -> dict[tuple[str, str, str], dict[str, str]]:
    indexed: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = row_key(row)
        if key in indexed:
            raise ValueError(f"{source}: duplicate row for {key[0]}/{key[1]}/{key[2]}")
        indexed[key] = row
    return indexed


def changed_grouping_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row["outer_reordered"] == "1"]


def auditable_changed_grouping_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row["outer_reordered"] == "1" and row["baseline_proven_empty"] != "1"
    ]


def write_query_list(rows: Iterable[dict[str, str]], path: Path) -> int:
    paths = [row["sql_path"] for row in rows]
    invalid = [
        value
        for value in paths
        if not value or value == "-" or value.startswith("/") or ".." in Path(value).parts
    ]
    if invalid:
        raise ValueError(f"cannot write unsafe or missing SQL path: {invalid[0]!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{value}\n" for value in paths), encoding="utf-8")
    return len(paths)


def parse_number(value: str) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def parse_speedup(value: str) -> float | None:
    parsed = parse_number(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def numeric_columns_match(
    left: dict[str, str], right: dict[str, str], columns: Iterable[str]
) -> bool:
    for column in columns:
        left_value = parse_number(left[column])
        right_value = parse_number(right[column])
        if left_value is None or right_value is None:
            return False
        if not math.isclose(left_value, right_value, rel_tol=1e-9, abs_tol=1e-9):
            return False
    return True


def cost_columns_match(
    left: dict[str, str], right: dict[str, str], columns: Iterable[str]
) -> bool:
    for column in columns:
        left_value = parse_number(left[column])
        right_value = parse_number(right[column])
        if left_value is None or right_value is None:
            if left[column] != right[column]:
                return False
        elif not math.isclose(left_value, right_value, rel_tol=1e-9, abs_tol=1e-9):
            return False
    return True


def measured_speedup(row: dict[str, str], metric: str) -> float | None:
    off_time = parse_speedup(row[f"{metric}_off"])
    on_time = parse_speedup(row[f"{metric}_on"])
    if off_time is None or on_time is None:
        return None
    return off_time / on_time


def normal_gate_state(row: dict[str, str]) -> tuple[bool, bool]:
    selected = row["outer_yan_selected"] == "1" and row["selected_plan"] == "OUTERYAN"
    selected_valid = (
        selected
        and row["decision_reason"] in SELECT_REASONS
        and row["cost_gate_applied"] == "1"
        and row["gate_result"] == "PASS"
    )
    rejected_valid = (
        not selected
        and row["outer_yan_selected"] == "0"
        and row["selected_plan"] == "DUCKDB"
        and row["decision_reason"] in REJECT_REASONS
        and (
            (
                row["decision_reason"] == "COST_UNAVAILABLE"
                and row["cost_gate_applied"] == "0"
                and row["gate_result"] == "UNAVAILABLE"
            )
            or (
                row["decision_reason"] != "COST_UNAVAILABLE"
                and row["cost_gate_applied"] == "1"
                and row["gate_result"] == "FAIL"
            )
        )
    )
    return selected, row["selection_mode"] == "GATED" and (selected_valid or rejected_valid)


def speedup_outcome(value: str, material_speedup: float) -> str:
    parsed = parse_speedup(value)
    if parsed is None:
        return "unmeasured"
    if parsed >= material_speedup:
        return "faster"
    if parsed <= 1.0 / material_speedup:
        return "slower"
    return "neutral"


def gate_judgment(selected: bool, outcome: str) -> str:
    if outcome == "faster":
        return "true_positive" if selected else "false_negative"
    if outcome == "slower":
        return "false_positive" if selected else "true_negative"
    if outcome == "neutral":
        return "selected_neutral" if selected else "rejected_neutral"
    return "unmeasured"


def outcome_consensus(tm_outcome: str, t1_outcome: str) -> str:
    outcomes = {tm_outcome, t1_outcome}
    if "incorrect" in outcomes:
        return "incorrect_candidate"
    if "faster" in outcomes and "slower" in outcomes:
        return "thread_sensitive"
    if outcomes == {"faster"}:
        return "faster_both"
    if outcomes == {"slower"}:
        return "slower_both"
    if outcomes == {"neutral"}:
        return "neutral_both"
    if outcomes <= {"faster", "neutral"} and "faster" in outcomes:
        return "faster_with_neutral"
    if outcomes <= {"slower", "neutral"} and "slower" in outcomes:
        return "slower_with_neutral"
    return "unmeasured"


def audit_rows(
    normal_rows: Iterable[dict[str, str]],
    forced_rows: Iterable[dict[str, str]],
    forced_source: Path,
    material_speedup: float,
    primary_metric: str,
) -> list[dict[str, str]]:
    forced_by_key = index_rows(forced_rows, forced_source)
    output: list[dict[str, str]] = []
    for normal in auditable_changed_grouping_rows(normal_rows):
        forced = forced_by_key.get(row_key(normal))
        selected, normal_gate_valid = normal_gate_state(normal)
        if forced is None:
            output.append({
                "query": normal["query"],
                "family": normal["family"],
                "sql_path": normal["sql_path"],
                "effective_pass": normal["effective_pass"],
                "normal_decision": normal["decision_reason"],
                "normal_selected_plan": normal["selected_plan"],
                "normal_outer_yan_selected": normal["outer_yan_selected"],
                "forced_decision": "MISSING",
                "forced_selected_plan": "MISSING",
                "forced_correct": "MISSING",
                "forced_note": "missing forced result",
                "forced_reported_tm_speedup": "NA",
                "forced_reported_t1_speedup": "NA",
                "normal_gate_valid": str(normal_gate_valid).upper(),
                "forced_reorder_match": "FALSE",
                "query_match": "FALSE",
                "formula_match": "FALSE",
                "relation_count_match": "FALSE",
                "parameters_match": "FALSE",
                "costs_match": "FALSE",
                "result_rows_match": "FALSE",
                "baseline_cost": normal["baseline_cost"],
                "candidate_join_cost": normal["candidate_join_cost"],
                "semijoin_raw_cost": normal["semijoin_raw_cost"],
                "candidate_total": normal["candidate_total"],
                "raw_cost_ratio": normal["raw_cost_ratio"],
                "candidate_to_baseline_join_input_ratio": normal[
                    "candidate_to_baseline_join_input_ratio"
                ],
                "tm_off": "NA",
                "tm_on": "NA",
                "tm_speedup": "NA",
                "tm_outcome": "unmeasured",
                "tm_gate_judgment": "missing_forced_result",
                "t1_off": "NA",
                "t1_on": "NA",
                "t1_speedup": "NA",
                "t1_outcome": "unmeasured",
                "t1_gate_judgment": "missing_forced_result",
                "consensus": "unmeasured",
                "comparable": "FALSE",
                "primary_metric": primary_metric,
                "primary_gate_judgment": "missing_forced_result",
                "audit_note": "forced CSV has no matching family/sql_path row",
            })
            continue

        query_match = normal["query"] == forced["query"]
        formula_match = normal["formula_id"] == forced["formula_id"]
        relation_count_match = normal["relation_count"] == forced["relation_count"]
        parameters_match = numeric_columns_match(normal, forced, PARAMETER_COLUMNS)
        costs_match = cost_columns_match(normal, forced, COST_COLUMNS)
        result_rows_match = normal["rows"] == forced["rows"]
        forced_reorder_match = forced["outer_reordered"] == "1"
        forced_executed = (
            forced["selection_mode"] == "FORCE_OUTERYAN_DIAGNOSTIC"
            and forced["outer_yan_selected"] == "1"
            and forced["selected_plan"] == "OUTERYAN"
            and forced_reorder_match
            and forced["decision_reason"] == "FORCE_OUTERYAN_DIAGNOSTIC"
            and forced["cost_gate_applied"] == "0"
            and forced["gate_result"] == "SKIPPED"
        )
        correct = normal["correct"] == "TRUE" and forced["correct"] == "TRUE"
        inputs_match = (
            query_match
            and formula_match
            and relation_count_match
            and parameters_match
            and costs_match
            and result_rows_match
        )

        metric_results: dict[str, tuple[str, str, str]] = {}
        for metric in ("tm", "t1"):
            measured = measured_speedup(forced, metric)
            speedup = "NA" if measured is None else f"{measured:.12g}"
            if not normal_gate_valid:
                outcome, judgment = "unmeasured", "invalid_normal_gate_state"
            elif not inputs_match:
                outcome, judgment = "unmeasured", "input_mismatch"
            elif not forced_executed:
                outcome, judgment = "unmeasured", "candidate_unavailable"
            elif not correct:
                outcome = "incorrect"
                judgment = "unsafe_selection" if selected else "correct_rejection"
            else:
                outcome = speedup_outcome(speedup, material_speedup)
                judgment = gate_judgment(selected, outcome)
            metric_results[metric] = (speedup, outcome, judgment)

        comparable = normal_gate_valid and inputs_match and forced_executed and correct
        notes = []
        if not normal_gate_valid:
            notes.append("normal row is not a consistent GATED selection or rejection")
        if not inputs_match:
            notes.append("normal/forced query, result, or cost-model metadata differ")
        if not forced_executed:
            notes.append("forced run did not execute the OuterYan candidate")
        if not correct:
            notes.append("normal or forced result-equivalence check failed")
        if not notes:
            notes.append("comparable")

        output.append({
            "query": normal["query"],
            "family": normal["family"],
            "sql_path": normal["sql_path"],
            "effective_pass": normal["effective_pass"],
            "normal_decision": normal["decision_reason"],
            "normal_selected_plan": normal["selected_plan"],
            "normal_outer_yan_selected": normal["outer_yan_selected"],
            "forced_decision": forced["decision_reason"],
            "forced_selected_plan": forced["selected_plan"],
            "forced_correct": forced["correct"],
            "forced_note": forced["note"],
            "forced_reported_tm_speedup": forced["tm_speedup"],
            "forced_reported_t1_speedup": forced["t1_speedup"],
            "normal_gate_valid": str(normal_gate_valid).upper(),
            "forced_reorder_match": str(forced_reorder_match).upper(),
            "query_match": str(query_match).upper(),
            "formula_match": str(formula_match).upper(),
            "relation_count_match": str(relation_count_match).upper(),
            "parameters_match": str(parameters_match).upper(),
            "costs_match": str(costs_match).upper(),
            "result_rows_match": str(result_rows_match).upper(),
            "baseline_cost": normal["baseline_cost"],
            "candidate_join_cost": normal["candidate_join_cost"],
            "semijoin_raw_cost": normal["semijoin_raw_cost"],
            "candidate_total": normal["candidate_total"],
            "raw_cost_ratio": normal["raw_cost_ratio"],
            "candidate_to_baseline_join_input_ratio": normal[
                "candidate_to_baseline_join_input_ratio"
            ],
            "tm_off": forced["tm_off"],
            "tm_on": forced["tm_on"],
            "tm_speedup": metric_results["tm"][0],
            "tm_outcome": metric_results["tm"][1],
            "tm_gate_judgment": metric_results["tm"][2],
            "t1_off": forced["t1_off"],
            "t1_on": forced["t1_on"],
            "t1_speedup": metric_results["t1"][0],
            "t1_outcome": metric_results["t1"][1],
            "t1_gate_judgment": metric_results["t1"][2],
            "consensus": outcome_consensus(metric_results["tm"][1], metric_results["t1"][1]),
            "comparable": str(comparable).upper(),
            "primary_metric": primary_metric,
            "primary_gate_judgment": metric_results[primary_metric][2],
            "audit_note": "; ".join(notes),
        })
    return output


def write_audit(rows: Iterable[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def print_summary(
    rows: list[dict[str, str]],
    primary_metric: str,
    material_speedup: float,
    changed_total: int,
    proven_empty_excluded: int,
) -> None:
    print(f"changed_grouping_total={changed_total}")
    print(f"proven_empty_excluded={proven_empty_excluded}")
    print(f"auditable_changed_grouping_candidates={len(rows)}")
    print(f"material_speedup={material_speedup:.6g}")
    for metric in ("tm", "t1"):
        counts = Counter(row[f"{metric}_gate_judgment"] for row in rows)
        summary = " ".join(f"{key}={counts[key]}" for key in sorted(counts))
        print(f"{metric}: {summary}")
    primary = Counter(row["primary_gate_judgment"] for row in rows)
    summary = " ".join(f"{key}={primary[key]}" for key in sorted(primary))
    print(f"primary={primary_metric}: {summary}")
    consensus = Counter(row["consensus"] for row in rows)
    summary = " ".join(f"{key}={consensus[key]}" for key in sorted(consensus))
    print(f"consensus: {summary}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normal-csv", required=True, type=Path)
    parser.add_argument("--forced-csv", type=Path)
    parser.add_argument("--write-query-list", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--primary-metric", choices=("tm", "t1"), default="tm")
    parser.add_argument(
        "--material-speedup",
        type=float,
        default=1.10,
        help="minimum speedup treated as a material win; losses use its reciprocal",
    )
    parser.add_argument("--fail-on-misclassification", action="store_true")
    args = parser.parse_args()
    if args.material_speedup <= 1.0 or not math.isfinite(args.material_speedup):
        parser.error("--material-speedup must be finite and greater than 1")
    if args.forced_csv is None and args.write_query_list is None:
        parser.error("provide --forced-csv and/or --write-query-list")
    if args.output is not None and args.forced_csv is None:
        parser.error("--output requires --forced-csv")
    return args


def main() -> int:
    args = parse_args()
    try:
        normal_rows = load_csv(args.normal_csv, REQUIRED_NORMAL_COLUMNS)
        index_rows(normal_rows, args.normal_csv)
        changed = changed_grouping_rows(normal_rows)
        auditable = auditable_changed_grouping_rows(normal_rows)
        proven_empty_excluded = len(changed) - len(auditable)
        if args.write_query_list is not None:
            count = write_query_list(auditable, args.write_query_list)
            print(
                f"query_list={args.write_query_list} queries={count} "
                f"proven_empty_excluded={proven_empty_excluded}"
            )

        if args.forced_csv is None:
            return 0
        forced_rows = load_csv(args.forced_csv, REQUIRED_FORCED_COLUMNS)
        audited = audit_rows(
            normal_rows,
            forced_rows,
            args.forced_csv,
            args.material_speedup,
            args.primary_metric,
        )
        output = args.output or args.normal_csv.with_name(f"{args.normal_csv.stem}.cost_gate_audit.csv")
        write_audit(audited, output)
        print_summary(
            audited,
            args.primary_metric,
            args.material_speedup,
            len(changed),
            proven_empty_excluded,
        )
        print(f"audit_csv={output}")
        if args.fail_on_misclassification:
            failures = {
                "false_positive",
                "false_negative",
                "unsafe_selection",
                "missing_forced_result",
                "candidate_unavailable",
                "input_mismatch",
                "invalid_normal_gate_state",
            }
            if any(row["primary_gate_judgment"] in failures for row in audited):
                return 1
        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
