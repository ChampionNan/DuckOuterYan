#!/usr/bin/env python3
"""Build one strict, portable PGPlan comparison report from a corpus run."""

from __future__ import print_function

import argparse
import csv
from decimal import Decimal, InvalidOperation, localcontext
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile


STATUS_FIELDS = (
    "family",
    "query",
    "status",
    "phase",
    "detail",
    "plan",
    "result_dir",
)
TIMING_FIELDS = (
    "configuration",
    "median_seconds",
    "measured_runs",
    "threads",
)
CORRECTNESS_FIELDS = ("configuration", "rows")
CONFIGURATIONS = ("native", "pgplan", "outer_yan")
SELECTED_PLANS = ("DUCKDB", "OUTERYAN")
LOG_SEPARATOR = "=" * 100

# Keep the complete machine decision in the tabular report.  The human log
# below is only a presentation of these fields, never a second parser or an
# independently inferred result.
OY_KEYS = (
    "formula_id",
    "selection_mode",
    "default_filter_upper_bound_checked",
    "default_filter_upper_bound_selected",
    "full_reduction_cardinality_lower_bound_applied",
    "uncertain_filter_amplification_guard",
    "stretch_cost_gate_eligible",
    "stretch_cost_gate_selected",
    "selected_plan",
    "outer_reordered",
    "cost_gate_applied",
    "outer_yan_selected",
    "baseline_proven_empty",
    "reason",
    "raw_cost_winner",
    "gate_result",
    "baseline_cost",
    "baseline_join_input_rows",
    "candidate_join_input_rows",
    "candidate_to_baseline_join_input_ratio",
    "semijoin_retained_cardinality_ratio",
    "uncertain_filter_cardinality_amplification",
    "candidate_join_cost",
    "semijoin_raw_cost",
    "semijoin_cost_ratio",
    "weighted_semijoin_cost",
    "candidate_total",
    "cost_ratio_limit",
    "baseline_threshold",
    "round1_build",
    "round1_probe",
    "round2_build",
    "round2_probe",
    "round1_pairs",
    "round1_filters",
    "round2_pairs",
    "round2_filters",
    "raw_cost_delta",
    "raw_cost_ratio",
    "gate_lhs",
    "gate_rhs",
    "gate_margin",
    "inner_output_weight",
    "unmatched_left_weight",
    "unmatched_right_weight",
    "semijoin_materialize_weight",
    "semijoin_filter_build_weight",
    "semijoin_replay_weight",
    "semijoin_probe_lookup_weight",
    "semijoin_probe_emit_weight",
)

# This prefix is the public CSV contract of experiment_onoff.sh.  Keep the
# spelling and order byte-for-byte compatible so existing analysis scripts can
# read a PGPlan comparison result by ignoring the appended fields.
ORIGINAL_CSV_FIELDS = (
    "query", "family", "sql_path", "relation_count", "reorder",
    "outer_reordered", "cost_gate_applied", "outer_yan_selected",
    "selected_plan", "baseline_proven_empty", "decision_reason", "formula_id",
    "selection_mode", "raw_cost_winner", "gate_result",
    "default_filter_upper_bound_checked", "default_filter_upper_bound_selected",
    "full_reduction_cardinality_lower_bound_applied",
    "uncertain_filter_amplification_guard", "stretch_cost_gate_eligible",
    "stretch_cost_gate_selected", "baseline_join_input_rows",
    "candidate_join_input_rows", "candidate_to_baseline_join_input_ratio",
    "semijoin_retained_cardinality_ratio",
    "uncertain_filter_cardinality_amplification", "baseline_cost",
    "candidate_join_cost", "semijoin_raw_cost", "semijoin_cost_ratio",
    "weighted_semijoin_cost", "candidate_total", "cost_ratio_limit",
    "baseline_threshold", "round1_build", "round1_probe", "round2_build",
    "round2_probe", "round1_pairs", "round1_filters", "round2_pairs",
    "round2_filters", "raw_cost_delta", "raw_cost_ratio", "gate_lhs",
    "gate_rhs", "gate_margin", "inner_output_weight", "unmatched_left_weight",
    "unmatched_right_weight", "semijoin_materialize_weight",
    "semijoin_filter_build_weight", "semijoin_replay_weight",
    "semijoin_probe_lookup_weight", "semijoin_probe_emit_weight", "kernel",
    "kernel_detail", "kernel_hash_reasons", "correct", "note", "t1_off",
    "t1_on", "t1_speedup", "tm_off", "tm_on", "tm_speedup",
    "profile_round1_operator_s", "profile_round2_operator_s",
    "profile_round3_operator_s", "profile_round1_operator_count",
    "profile_round2_operator_count", "profile_round3_operator_count",
    "profile_total_time_s", "profile_round1_ratio", "profile_round2_ratio",
    "profile_total_sj_ratio", "profile_round3_ratio",
    "profile_other_elapsed_s", "profile_other_ratio", "profile_timed_samples",
    "rows", "effective_pass", "duckdb_plan", "enabled_plan", "trace_file",
    "cost_file", "profile_threads", "profile_cpu_time_s",
)

# PostgreSQL and corpus bookkeeping are additive.  In particular, do not
# rename or repurpose an original column to carry the third configuration.
PGPLAN_CSV_FIELDS = (
    "pgplan_status",
    "pgplan_plan",
    "pgplan_target_verification",
    "pgplan_correctness_verification",
    "pgplan_expected_semantic_signature",
    "pgplan_final_semantic_signature",
    "pgplan_implied_equality_count",
    "pgplan_correctness_expected_semantic_signature",
    "pgplan_correctness_final_semantic_signature",
    "pgplan_correctness_implied_equality_count",
    "tm_pgplan",
    "tm_native_vs_pgplan_speedup",
    "t1_pgplan",
    "t1_native_vs_pgplan_speedup",
)
COMPARISON_CSV_FIELDS = (
    "pgplan_comparison_mode",
    "pgplan_correctness_comparison_set",
    "pgplan_comparison_status",
    "pgplan_comparison_phase",
    "pgplan_comparison_detail",
    "pgplan_correctness_scope",
    "pgplan_correctness_status",
    "pgplan_correctness_sha256",
    "pgplan_correctness_hash_rows",
    "pgplan_correctness_outer_yan_selected_plan",
    "pgplan_comparison_measured_runs",
    "pgplan_comparison_threads",
    "pgplan_comparison_result_dir",
    "pgplan_comparison_status_plan",
    "pgplan_comparison_diagnostic_log",
    "pgplan_comparison_ordinal",
    "pgplan_comparison_total",
    "pgplan_comparison_relations",
    "pgplan_comparison_join_count",
    "pgplan_correctness_origin",
    "pgplan_correctness_comparison_executed",
    "pgplan_correctness_reuse_source",
    "pgplan_correctness_receipt_sha256",
    "pgplan_correctness_reuse_source_receipt_sha256",
    "pgplan_correctness_reuse_source_manifest_sha256",
)
COMPARISON_FIELDS = ORIGINAL_CSV_FIELDS + PGPLAN_CSV_FIELDS + COMPARISON_CSV_FIELDS

LEGACY_OY_FIELD_MAP = {
    "outer_reordered": "outer_reordered",
    "cost_gate_applied": "cost_gate_applied",
    "outer_yan_selected": "outer_yan_selected",
    "selected_plan": "selected_plan",
    "baseline_proven_empty": "baseline_proven_empty",
    "decision_reason": "reason",
    "formula_id": "formula_id",
    "selection_mode": "selection_mode",
    "raw_cost_winner": "raw_cost_winner",
    "gate_result": "gate_result",
    "default_filter_upper_bound_checked": "default_filter_upper_bound_checked",
    "default_filter_upper_bound_selected": "default_filter_upper_bound_selected",
    "full_reduction_cardinality_lower_bound_applied": (
        "full_reduction_cardinality_lower_bound_applied"
    ),
    "uncertain_filter_amplification_guard": "uncertain_filter_amplification_guard",
    "stretch_cost_gate_eligible": "stretch_cost_gate_eligible",
    "stretch_cost_gate_selected": "stretch_cost_gate_selected",
    "baseline_join_input_rows": "baseline_join_input_rows",
    "candidate_join_input_rows": "candidate_join_input_rows",
    "candidate_to_baseline_join_input_ratio": (
        "candidate_to_baseline_join_input_ratio"
    ),
    "semijoin_retained_cardinality_ratio": "semijoin_retained_cardinality_ratio",
    "uncertain_filter_cardinality_amplification": (
        "uncertain_filter_cardinality_amplification"
    ),
    "baseline_cost": "baseline_cost",
    "candidate_join_cost": "candidate_join_cost",
    "semijoin_raw_cost": "semijoin_raw_cost",
    "semijoin_cost_ratio": "semijoin_cost_ratio",
    "weighted_semijoin_cost": "weighted_semijoin_cost",
    "candidate_total": "candidate_total",
    "cost_ratio_limit": "cost_ratio_limit",
    "baseline_threshold": "baseline_threshold",
    "round1_build": "round1_build",
    "round1_probe": "round1_probe",
    "round2_build": "round2_build",
    "round2_probe": "round2_probe",
    "round1_pairs": "round1_pairs",
    "round1_filters": "round1_filters",
    "round2_pairs": "round2_pairs",
    "round2_filters": "round2_filters",
    "raw_cost_delta": "raw_cost_delta",
    "raw_cost_ratio": "raw_cost_ratio",
    "gate_lhs": "gate_lhs",
    "gate_rhs": "gate_rhs",
    "gate_margin": "gate_margin",
    "inner_output_weight": "inner_output_weight",
    "unmatched_left_weight": "unmatched_left_weight",
    "unmatched_right_weight": "unmatched_right_weight",
    "semijoin_materialize_weight": "semijoin_materialize_weight",
    "semijoin_filter_build_weight": "semijoin_filter_build_weight",
    "semijoin_replay_weight": "semijoin_replay_weight",
    "semijoin_probe_lookup_weight": "semijoin_probe_lookup_weight",
    "semijoin_probe_emit_weight": "semijoin_probe_emit_weight",
}
SUMMARY_FIELDS = (
    "family",
    "selected_queries",
    "pass_queries",
    "skip_queries",
    "fail_queries",
    "timed_queries",
    "pgplan_speedup_vs_native_geomean",
    "outer_yan_speedup_vs_native_geomean",
    "pgplan_faster_than_native",
    "outer_yan_faster_than_native",
)


class ReportError(Exception):
    """A corpus artifact is missing, malformed, or internally inconsistent."""


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate DuckDB, PGPlan, and OuterYan medians from a completed "
            "corpus result directory."
        )
    )
    parser.add_argument(
        "--result-dir",
        required=True,
        help="corpus output directory containing status.tsv and runs/",
    )
    parser.add_argument(
        "--print-row",
        type=int,
        help="print one 1-based legacy-style detail block and write no reports",
    )
    parser.add_argument(
        "--total",
        type=int,
        help="display denominator used with --print-row",
    )
    arguments = parser.parse_args(argv)
    if (arguments.print_row is None) != (arguments.total is None):
        parser.error("--print-row and --total must be supplied together")
    if arguments.print_row is not None and arguments.print_row < 1:
        parser.error("--print-row must be at least 1")
    if arguments.total is not None and arguments.total < arguments.print_row:
        parser.error("--total must be at least --print-row")
    return arguments


def read_tsv(path, expected_fields):
    try:
        source = path.open("r", encoding="utf-8", newline="")
    except OSError as error:
        raise ReportError("cannot read {0}: {1}".format(path, error))
    with source:
        reader = csv.DictReader(source, delimiter="\t")
        if tuple(reader.fieldnames or ()) != tuple(expected_fields):
            raise ReportError(
                "{0}: expected header {1}, found {2}".format(
                    path,
                    "\\t".join(expected_fields),
                    "\\t".join(reader.fieldnames or ()),
                )
            )
        rows = []
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(row[field] is None for field in expected_fields):
                raise ReportError(
                    "{0}:{1}: malformed TSV row".format(path, line_number)
                )
            row["_line_number"] = line_number
            rows.append(row)
        return rows


def positive_integer(value, path, line_number, field):
    if not re.match(r"^[1-9][0-9]*$", value):
        raise ReportError(
            "{0}:{1}: {2} must be a positive integer, found {3!r}".format(
                path, line_number, field, value
            )
        )
    return int(value)


def nonnegative_integer(value, path, line_number, field):
    if not re.match(r"^(0|[1-9][0-9]*)$", value):
        raise ReportError(
            "{0}:{1}: {2} must be a non-negative integer, found {3!r}".format(
                path, line_number, field, value
            )
        )
    return int(value)


def positive_decimal(value, path, line_number):
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise ReportError(
            "{0}:{1}: median_seconds is not numeric: {2!r}".format(
                path, line_number, value
            )
        )
    if not parsed.is_finite() or parsed <= 0:
        raise ReportError(
            "{0}:{1}: median_seconds must be finite and positive, found {2!r}".format(
                path, line_number, value
            )
        )
    return parsed


def rows_for_configurations(rows, path, expected):
    by_configuration = {}
    for row in rows:
        configuration = row["configuration"]
        if configuration not in expected:
            raise ReportError(
                "{0}:{1}: unsupported configuration {2!r}".format(
                    path, row["_line_number"], configuration
                )
            )
        if configuration in by_configuration:
            raise ReportError(
                "{0}:{1}: duplicate configuration {2!r}".format(
                    path, row["_line_number"], configuration
                )
            )
        by_configuration[configuration] = row
    missing = [name for name in expected if name not in by_configuration]
    if missing or len(rows) != len(expected):
        raise ReportError(
            "{0}: expected exactly {1}; missing {2}".format(
                path, ", ".join(expected),
                ", ".join(missing) if missing else "none"
            )
        )
    return by_configuration


def rows_by_configuration(rows, path):
    return rows_for_configurations(rows, path, CONFIGURATIONS)


def read_manifest(path):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ReportError("cannot read {0}: {1}".format(path, error))
    values = {}
    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        key, separator, value = line.partition("=")
        if not separator or not key:
            raise ReportError(
                "{0}:{1}: expected key=value".format(path, line_number)
            )
        if key in values:
            raise ReportError(
                "{0}:{1}: duplicate manifest key {2!r}".format(
                    path, line_number, key
                )
            )
        values[key] = value
    target_key = "outer_yan_selected_plan"
    if target_key not in values:
        raise ReportError("{0}: missing manifest key {1}".format(path, target_key))
    if values[target_key] not in SELECTED_PLANS:
        raise ReportError(
            "{0}: {1} must be DUCKDB or OUTERYAN, found {2!r}".format(
                path, target_key, values[target_key]
            )
        )

    # Correctness-database plan selection was added after the first PGPlan
    # result format. Keep old completed runs reportable, while validating the
    # value strictly whenever the newer provenance field is present.
    correctness_key = "correctness_outer_yan_selected_plan"
    if (
        correctness_key in values
        and values[correctness_key] not in SELECTED_PLANS
    ):
        raise ReportError(
            "{0}: {1} must be DUCKDB or OUTERYAN, found {2!r}".format(
                path, correctness_key, values[correctness_key]
            )
        )
    return values


def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise ReportError("cannot read {0}: {1}".format(path, error))


def correctness_scope_from_manifest(manifest):
    """Classify the database scope covered by the correctness evidence."""
    if manifest.get("correctness_origin") == "NOT_RUN":
        return "not-run"
    recorded_scope = manifest.get("correctness_scope", "")
    if recorded_scope:
        if recorded_scope not in ("target", "bounded", "not-run"):
            raise ReportError(
                "correctness_scope must be target, bounded, or not-run, "
                "found {0!r}".format(
                    recorded_scope
                )
            )
        return recorded_scope
    correctness_db = manifest.get("correctness_db", "")
    execution_db = manifest.get("execution_db", "")
    # Before correctness_db was added, experiment.sh used execution_db for
    # correctness too. Preserve that provenance instead of calling it bounded.
    if not correctness_db:
        return "target"
    if execution_db and os.path.normpath(correctness_db) == os.path.normpath(execution_db):
        return "target"
    return "bounded"


def correctness_provenance_from_manifest(manifest):
    """Read explicit fresh/reused correctness provenance when it exists.

    Runs produced before sealed correctness receipts have none of these keys.
    Keep those legacy artifacts reportable with empty additive columns instead
    of guessing whether their comparison was executed in the reported run.
    """
    fields = {
        "comparison_mode": "",
        "correctness_comparison_set": "",
        "correctness_origin": "",
        "correctness_comparison_executed": "",
        "correctness_reuse_source": "",
        "correctness_receipt_sha256": "",
        "correctness_reuse_source_receipt_sha256": "",
        "correctness_reuse_source_manifest_sha256": "",
    }
    provenance_keys = tuple(fields)
    if not any(key in manifest for key in provenance_keys):
        return fields

    comparison_mode = manifest.get("comparison_mode", "both")
    if comparison_mode not in ("both", "pgplan-only", "none"):
        raise ReportError(
            "comparison_mode must be both, pgplan-only, or none, "
            "found {0!r}".format(comparison_mode)
        )
    origin = manifest.get("correctness_origin", "")
    if origin not in ("FRESH", "PARTIAL", "NOT_RUN", "REUSED"):
        raise ReportError(
            "correctness_origin must be FRESH, PARTIAL, NOT_RUN, or REUSED, "
            "found {0!r}".format(origin)
        )
    comparison_executed = manifest.get(
        "correctness_comparison_executed", ""
    )
    legacy_comparison_set = {
        "FRESH": "both",
        "REUSED": "none",
    }.get(origin, "")
    comparison_set = manifest.get(
        "correctness_comparison_set", legacy_comparison_set
    )
    expected = {
        "FRESH": ("1", "both", "PASS"),
        "PARTIAL": ("1", "pgplan-only", "PARTIAL"),
        "NOT_RUN": ("0", "none", "NOT_RUN"),
        "REUSED": ("0", "none", "PASS"),
    }
    expected_comparison, expected_set, expected_status = expected[origin]
    if comparison_executed != expected_comparison:
        raise ReportError(
            "correctness_comparison_executed must be {0} for {1}, found {2!r}".format(
                expected_comparison, origin, comparison_executed
            )
        )
    if comparison_set != expected_set:
        raise ReportError(
            "correctness_comparison_set must be {0} for {1}, found {2!r}".format(
                expected_set, origin, comparison_set
            )
        )
    legacy_status = "PASS" if origin in ("FRESH", "REUSED") else ""
    manifest_status = manifest.get("correctness_status", legacy_status)
    if manifest_status != expected_status:
        raise ReportError(
            "correctness_status must be {0} for {1}, found {2!r}".format(
                expected_status, origin, manifest_status
            )
        )

    receipt_sha = manifest.get("correctness_receipt_sha256", "")
    sha_fields = []
    reuse_source = manifest.get("correctness_reuse_source", "")
    source_receipt_sha = manifest.get(
        "correctness_reuse_source_receipt_sha256", ""
    )
    source_manifest_sha = manifest.get(
        "correctness_reuse_source_manifest_sha256", ""
    )
    if origin == "REUSED":
        if not reuse_source:
            raise ReportError(
                "correctness_reuse_source is required for REUSED correctness"
            )
        sha_fields.extend(
            (
                ("correctness_receipt_sha256", receipt_sha),
                (
                    "correctness_reuse_source_receipt_sha256",
                    source_receipt_sha,
                ),
                (
                    "correctness_reuse_source_manifest_sha256",
                    source_manifest_sha,
                ),
            )
        )
    else:
        unexpected_reuse = [
            key
            for key, value in (
                ("correctness_reuse_source", reuse_source),
                (
                    "correctness_reuse_source_receipt_sha256",
                    source_receipt_sha,
                ),
                (
                    "correctness_reuse_source_manifest_sha256",
                    source_manifest_sha,
                ),
            )
            if value
        ]
        if unexpected_reuse:
            raise ReportError(
                "non-reused correctness must not contain reuse provenance: {0}".format(
                    ", ".join(unexpected_reuse)
                )
            )
        if origin == "FRESH" and receipt_sha:
            sha_fields.append(("correctness_receipt_sha256", receipt_sha))
        elif origin != "FRESH" and receipt_sha:
            raise ReportError(
                "{0} correctness must not contain a reusable receipt".format(origin)
            )
    for key, value in sha_fields:
        if not re.match(r"^[0-9a-fA-F]{64}$", value):
            raise ReportError(
                "{0} must be a SHA-256 digest, found {1!r}".format(key, value)
            )
    if origin == "REUSED" and receipt_sha.lower() != source_receipt_sha.lower():
        raise ReportError(
            "REUSED correctness receipt/source receipt SHA-256 values differ"
        )

    fields.update(
        {
            "comparison_mode": comparison_mode,
            "correctness_comparison_set": comparison_set,
            "correctness_origin": origin,
            "correctness_comparison_executed": comparison_executed,
            "correctness_reuse_source": reuse_source,
            "correctness_receipt_sha256": receipt_sha.lower(),
            "correctness_reuse_source_receipt_sha256": (
                source_receipt_sha.lower() if source_receipt_sha else ""
            ),
            "correctness_reuse_source_manifest_sha256": (
                source_manifest_sha.lower() if source_manifest_sha else ""
            ),
        }
    )
    return fields


def read_manifest_loose(path):
    """Best-effort key/value reader for a run that terminated mid-experiment."""
    if not path.exists():
        return {}
    try:
        lines = read_text(path).splitlines()
    except ReportError:
        return {}
    values = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key and key not in values:
            values[key] = value
    return values


def read_oy_trace(path, required=True):
    if not path.exists():
        if required:
            raise ReportError("cannot read {0}: file does not exist".format(path))
        return {}, ""
    records = []
    raw_records = []
    for line_number, line in enumerate(read_text(path).splitlines(), start=1):
        if not line.startswith("[OY_DECISION]"):
            continue
        payload = line[len("[OY_DECISION]") :].strip()
        values = {}
        for match in re.finditer(r"(?:^|\s)([A-Za-z0-9_]+)=([^\s]+)", payload):
            key, value = match.group(1), match.group(2)
            if key in values:
                raise ReportError(
                    "{0}:{1}: duplicate OuterYan field {2!r}".format(
                        path, line_number, key
                    )
                )
            values[key] = value
        if not values:
            raise ReportError(
                "{0}:{1}: malformed [OY_DECISION] record".format(path, line_number)
            )
        records.append(values)
        raw_records.append(line)
    if not records:
        if required:
            raise ReportError("{0}: contains no [OY_DECISION] record".format(path))
        return {}, ""
    # A single bare query must have one optimizer decision. Multiple records
    # would make the selected-plan cross-check ambiguous.
    if len(records) != 1:
        raise ReportError(
            "{0}: expected one [OY_DECISION] record, found {1}".format(
                path, len(records)
            )
        )
    return records[0], raw_records[0]


def read_pgplan_trace(path, required=True):
    if not path.exists():
        if required:
            raise ReportError("cannot read {0}: file does not exist".format(path))
        return {}, "", "NA"
    events = {}
    raw_records = []
    for line_number, line in enumerate(read_text(path).splitlines(), start=1):
        if not line.startswith("[PGPLAN]"):
            continue
        payload = line[len("[PGPLAN]") :].strip()
        try:
            record = json.loads(payload)
        except (TypeError, ValueError) as error:
            raise ReportError(
                "{0}:{1}: invalid [PGPLAN] JSON: {2}".format(
                    path, line_number, error
                )
            )
        if not isinstance(record, dict) or not isinstance(record.get("event"), str):
            raise ReportError(
                "{0}:{1}: [PGPLAN] record has no string event".format(
                    path, line_number
                )
            )
        event = record["event"]
        if event not in ("imported", "verified"):
            continue
        if event in events:
            raise ReportError(
                "{0}:{1}: duplicate [PGPLAN] event {2!r}".format(
                    path, line_number, event
                )
            )
        events[event] = record
        raw_records.append(line)
    if not events:
        if required:
            raise ReportError("{0}: contains no PGPlan import records".format(path))
        return {}, "", "NA"
    missing = [event for event in ("imported", "verified") if event not in events]
    if missing:
        raise ReportError(
            "{0}: missing [PGPLAN] event(s): {1}".format(path, ", ".join(missing))
        )
    imported = events["imported"]
    verified = events["verified"]
    artifact_raw = imported.get("artifact_raw_signature")
    imported_raw = imported.get("imported_raw_signature")
    expected = imported.get("expected_semantic_signature")
    verified_expected = verified.get("expected_semantic_signature")
    final = verified.get("final_semantic_signature")
    if not all(isinstance(value, str) and value for value in (
        artifact_raw, imported_raw, expected, verified_expected, final
    )):
        raise ReportError("{0}: PGPlan signatures are missing or empty".format(path))
    if artifact_raw != imported_raw:
        raise ReportError("{0}: imported raw signature differs from artifact".format(path))
    if expected != verified_expected or verified_expected != final:
        raise ReportError("{0}: final semantic signature differs from expected".format(path))
    if imported.get("query_sha256_verified") is not True:
        raise ReportError("{0}: query SHA-256 was not verified".format(path))
    implied = imported.get("implied_equality_count", 0)
    if not isinstance(implied, int) or isinstance(implied, bool) or implied < 0:
        raise ReportError("{0}: invalid implied_equality_count".format(path))
    return {
        "artifact_raw_signature": artifact_raw,
        "imported_raw_signature": imported_raw,
        "expected_semantic_signature": expected,
        "final_semantic_signature": final,
        "implied_equality_count": str(implied),
    # Preserve both records while keeping every TSV/CSV query on one physical
    # line (the JSON payloads themselves contain no literal newlines).
    }, " || ".join(raw_records), "VERIFIED"


def read_artifact(path):
    try:
        document = json.loads(read_text(path))
    except (TypeError, ValueError) as error:
        raise ReportError("{0}: invalid JSON: {1}".format(path, error))
    if not isinstance(document, dict) or document.get("format") != "duckyan.pg_join_tree.v1":
        raise ReportError("{0}: unsupported or missing artifact format".format(path))
    relation_labels = []
    join_count = [0]

    def visit(node, location):
        if not isinstance(node, dict):
            raise ReportError("{0}: {1} must be an object".format(path, location))
        operation = node.get("op")
        if operation == "scan":
            relation = node.get("relation")
            if not isinstance(relation, str) or not relation:
                raise ReportError("{0}: {1}.relation must be non-empty".format(path, location))
            schema = node.get("schema", "")
            alias = node.get("alias", "")
            label = (schema + "." if schema else "") + relation
            if alias:
                label += " AS " + str(alias)
            relation_labels.append(label)
            return
        if operation == "join":
            join_count[0] += 1
            visit(node.get("left"), location + ".left")
            visit(node.get("right"), location + ".right")
            return
        raise ReportError("{0}: {1}.op is not scan or join".format(path, location))

    visit(document.get("tree"), "tree")
    return {
        "artifact_path": str(path.resolve()),
        "relation_count": str(len(relation_labels)),
        "join_count": str(join_count[0]),
        "relations": " | ".join(relation_labels),
    }


def read_correctness(run_dir, correctness_rows, required):
    status_path = run_dir / "correctness" / "status.txt"
    hash_path = run_dir / "correctness" / "multiset_sha256.tsv"
    if not status_path.exists() or not hash_path.exists():
        if required:
            missing = status_path if not status_path.exists() else hash_path
            raise ReportError("cannot read {0}: file does not exist".format(missing))
        return {"correctness_status": "", "correctness_sha256": "", "correctness_hash_rows": ""}
    status_text = read_text(status_path).strip()
    if not (
        status_text.startswith("PASS")
        or status_text.startswith("PARTIAL")
    ):
        raise ReportError(
            "{0}: PASS or PARTIAL status required".format(status_path)
        )
    hash_rows = read_tsv(hash_path, ("sha256", "rows"))
    if len(hash_rows) != 1:
        raise ReportError("{0}: expected exactly one hash row".format(hash_path))
    digest = hash_rows[0]["sha256"]
    if not re.match(r"^[0-9a-fA-F]{64}$", digest):
        raise ReportError("{0}: invalid SHA-256 digest".format(hash_path))
    hashed_rows = str(nonnegative_integer(
        hash_rows[0]["rows"], hash_path, hash_rows[0]["_line_number"], "rows"
    ))
    if correctness_rows and correctness_rows != hashed_rows:
        raise ReportError("{0}: hash row count differs from correctness rows".format(hash_path))
    return {
        "correctness_status": status_text,
        "correctness_sha256": digest.lower(),
        "correctness_hash_rows": hashed_rows,
    }


def read_nonpass_correctness(result_root, status_row):
    """Read any correctness evidence produced before a later failure/timeout."""
    query_path = PurePosixPath(status_row["query"])
    candidates = [result_root / "runs" / status_row["family"] / query_path.stem]
    if status_row["result_dir"]:
        recorded = Path(status_row["result_dir"])
        if not recorded.is_absolute():
            recorded = result_root / recorded
        if recorded not in candidates:
            candidates.append(recorded)
    run_dir = next((candidate for candidate in candidates if candidate.is_dir()), None)
    if run_dir is None:
        return {}

    correctness_dir = run_dir / "correctness"
    status_path = correctness_dir / "status.txt"
    comparison_paths = (
        correctness_dir / "pgplan.comparison.txt",
        correctness_dir / "outer_yan.comparison.txt",
    )
    status_text = ""
    if status_path.exists():
        try:
            status_text = read_text(status_path).strip()
        except ReportError:
            status_text = ""
    mismatch = False
    for comparison_path in comparison_paths:
        if not comparison_path.exists():
            continue
        try:
            mismatch = mismatch or read_text(comparison_path).lstrip().startswith("FAIL")
        except ReportError:
            pass
    if not status_text and not mismatch:
        return {}

    manifest = read_manifest_loose(run_dir / "provenance" / "manifest.txt")
    try:
        correctness_provenance = correctness_provenance_from_manifest(manifest)
    except ReportError:
        # A non-PASS run can terminate while appending provenance. Preserve the
        # terminal failure row without presenting a partial receipt as valid.
        correctness_provenance = correctness_provenance_from_manifest({})
    try:
        correctness_scope = correctness_scope_from_manifest(manifest)
    except ReportError:
        correctness_scope = ""
    output = {
        "correct": "FALSE" if mismatch or status_text.startswith("FAIL") else (
            "TRUE" if status_text.startswith("PASS") else "NA"
        ),
        "correctness_scope": correctness_scope,
        "correctness_status": status_text or "FAIL: multiset comparison mismatch",
        "result_dir": str(run_dir.resolve()),
    }
    output.update(correctness_provenance)
    rows_path = correctness_dir / "row_counts.tsv"
    if rows_path.exists():
        try:
            comparison_set = correctness_provenance.get(
                "correctness_comparison_set", ""
            )
            expected_configs = (
                ("native", "pgplan")
                if comparison_set == "pgplan-only"
                else CONFIGURATIONS
            )
            table = rows_for_configurations(
                read_tsv(rows_path, CORRECTNESS_FIELDS), rows_path,
                expected_configs,
            )
            values = set(table[name]["rows"] for name in expected_configs)
            if len(values) == 1 and re.match(r"^(0|[1-9][0-9]*)$", next(iter(values))):
                output["correctness_rows"] = next(iter(values))
        except ReportError:
            pass
    hash_path = correctness_dir / "multiset_sha256.tsv"
    if hash_path.exists():
        try:
            hash_rows = read_tsv(hash_path, ("sha256", "rows"))
            if len(hash_rows) == 1 and re.match(
                r"^[0-9a-fA-F]{64}$", hash_rows[0]["sha256"]
            ):
                output["correctness_sha256"] = hash_rows[0]["sha256"].lower()
                output["correctness_hash_rows"] = hash_rows[0]["rows"]
        except ReportError:
            pass
    return output


def resolve_run_dir(result_root, status_row):
    query_path = PurePosixPath(status_row["query"])
    if query_path.suffix != ".sql" or not query_path.stem:
        raise ReportError(
            "status.tsv:{0}: PASS query must end in .sql: {1!r}".format(
                status_row["_line_number"], status_row["query"]
            )
        )

    # Prefer the canonical location under the supplied root. This keeps a
    # copied result directory self-contained even when status.tsv retains the
    # absolute path of the machine that produced it.
    canonical = result_root / "runs" / status_row["family"] / query_path.stem
    candidates = [canonical]
    recorded_text = status_row["result_dir"]
    if not recorded_text:
        raise ReportError(
            "status.tsv:{0}: PASS row has an empty result_dir".format(
                status_row["_line_number"]
            )
        )
    recorded = Path(recorded_text)
    if not recorded.is_absolute():
        recorded = result_root / recorded
    if recorded != canonical:
        candidates.append(recorded)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise ReportError(
        "status.tsv:{0}: PASS result directory does not exist (tried {1})".format(
            status_row["_line_number"], ", ".join(str(path) for path in candidates)
        )
    )


def read_timing_artifact(path, required=True):
    """Read one three-configuration CLI-timer summary."""
    if not path.exists():
        if required:
            raise ReportError("cannot read {0}: file does not exist".format(path))
        return None
    timing_rows = read_tsv(path, TIMING_FIELDS)
    timing = rows_by_configuration(timing_rows, path)
    medians = {}
    median_text = {}
    runs = set()
    threads = set()
    for configuration in CONFIGURATIONS:
        row = timing[configuration]
        row_line = row["_line_number"]
        medians[configuration] = positive_decimal(
            row["median_seconds"], path, row_line
        )
        median_text[configuration] = row["median_seconds"]
        runs.add(
            positive_integer(
                row["measured_runs"], path, row_line, "measured_runs"
            )
        )
        threads.add(
            positive_integer(row["threads"], path, row_line, "threads")
        )
    if len(runs) != 1:
        raise ReportError("{0}: measured_runs differs across configurations".format(path))
    if len(threads) != 1:
        raise ReportError("{0}: threads differs across configurations".format(path))
    return {
        "medians": medians,
        "median_text": median_text,
        "measured_runs": next(iter(runs)),
        "threads": next(iter(threads)),
    }


def read_pass_artifacts(result_root, status_row):
    run_dir = resolve_run_dir(result_root, status_row)
    timing_path = run_dir / "timing" / "summary.tsv"
    timing = read_timing_artifact(timing_path)
    t1_path = run_dir / "timing" / "t1_summary.tsv"
    t1_timing = read_timing_artifact(t1_path, required=False)
    if t1_timing is not None:
        if t1_timing["threads"] != 1:
            raise ReportError("{0}: every T1 configuration must use one thread".format(t1_path))
        if t1_timing["measured_runs"] != 1:
            raise ReportError(
                "{0}: every T1 configuration must use one measured run".format(
                    t1_path
                )
            )

    manifest = read_manifest(run_dir / "provenance" / "manifest.txt")
    correctness_provenance = correctness_provenance_from_manifest(manifest)
    comparison_set = correctness_provenance["correctness_comparison_set"]
    if not comparison_set:
        # Runs created before comparison modes always checked all three
        # configurations when row-count evidence exists.
        comparison_set = "both"

    correctness_rows = ""
    correctness_path = run_dir / "correctness" / "row_counts.tsv"
    if correctness_path.exists():
        expected_correctness_configs = (
            ("native", "pgplan")
            if comparison_set == "pgplan-only"
            else CONFIGURATIONS
        )
        correctness_table = rows_for_configurations(
            read_tsv(correctness_path, CORRECTNESS_FIELDS), correctness_path,
            expected_correctness_configs,
        )
        row_counts = set()
        for configuration in expected_correctness_configs:
            row = correctness_table[configuration]
            row_counts.add(
                nonnegative_integer(
                    row["rows"], correctness_path, row["_line_number"], "rows"
                )
            )
        if len(row_counts) != 1:
            raise ReportError(
                "{0}: correctness row counts differ across configurations".format(
                    correctness_path
                )
            )
        correctness_rows = str(next(iter(row_counts)))

    current_format = bool(correctness_provenance["correctness_origin"])
    comparison_ran = comparison_set in ("both", "pgplan-only")
    if current_format and comparison_ran and correctness_rows == "":
        raise ReportError(
            "{0}: current-format PASS is missing correctness/row_counts.tsv".format(
                run_dir
            )
        )

    artifact = read_artifact(run_dir / "provenance" / "postgres_plan.json")
    oy_values, oy_raw = read_oy_trace(
        run_dir / "traces" / "outer_yan_decision.trace"
    )
    trace_selected = oy_values.get("selected_plan")
    if trace_selected not in SELECTED_PLANS:
        raise ReportError(
            "{0}: OuterYan trace selected_plan must be DUCKDB or OUTERYAN".format(
                run_dir
            )
        )
    if trace_selected != manifest["outer_yan_selected_plan"]:
        raise ReportError(
            "{0}: manifest/OuterYan trace selected-plan mismatch ({1} != {2})".format(
                run_dir, manifest["outer_yan_selected_plan"], trace_selected
            )
        )

    target_pg, unused_target_pg_raw, target_pg_verified = read_pgplan_trace(
        run_dir / "traces" / "pgplan_explain.trace"
    )
    require_correctness_pgplan = current_format and (
        comparison_ran or correctness_provenance["correctness_origin"] == "REUSED"
    )
    correctness_pg, unused_correctness_pg_raw, correctness_pg_verified = read_pgplan_trace(
        run_dir / "traces" / "pgplan_correctness.trace",
        required=require_correctness_pgplan,
    )
    correctness_oy_path = run_dir / "traces" / "outer_yan_correctness_decision.trace"
    if not correctness_oy_path.exists():
        correctness_oy_path = run_dir / "traces" / "outer_yan_correctness.trace"
    require_correctness_outer_yan = current_format and (
        comparison_set == "both"
        or correctness_provenance["correctness_origin"] == "REUSED"
    )
    correctness_oy, unused_correctness_oy_raw = read_oy_trace(
        correctness_oy_path, required=require_correctness_outer_yan
    )
    if require_correctness_outer_yan:
        correctness_selected = correctness_oy.get("selected_plan")
        if correctness_selected != manifest["correctness_outer_yan_selected_plan"]:
            raise ReportError(
                "{0}: correctness manifest/OuterYan trace selected-plan mismatch "
                "({1} != {2})".format(
                    run_dir,
                    manifest["correctness_outer_yan_selected_plan"],
                    correctness_selected,
                )
            )
    correctness = read_correctness(
        run_dir, correctness_rows, required=(current_format and comparison_ran)
    )
    result = {
        "run_dir": str(run_dir),
        "medians": timing["medians"],
        "median_text": timing["median_text"],
        "measured_runs": str(timing["measured_runs"]),
        "threads": str(timing["threads"]),
        "t1_medians": t1_timing["medians"] if t1_timing is not None else None,
        "t1_median_text": (
            t1_timing["median_text"] if t1_timing is not None else None
        ),
        "correctness_rows": correctness_rows,
        "correctness_scope": correctness_scope_from_manifest(manifest),
        "timeout_seconds": manifest.get("timeout_seconds", ""),
        "outer_yan_selected_plan": manifest["outer_yan_selected_plan"],
        "correctness_outer_yan_selected_plan": manifest.get(
            "correctness_outer_yan_selected_plan", ""
        ),
        "oy_values": oy_values,
        "outer_yan_decision_raw": oy_raw,
        "pgplan_target": target_pg,
        "pgplan_target_verification": target_pg_verified,
        "pgplan_correctness": correctness_pg,
        "pgplan_correctness_verification": correctness_pg_verified,
    }
    result.update(artifact)
    result.update(correctness)
    result.update(correctness_provenance)
    return result


def speedup(numerator, denominator):
    with localcontext() as context:
        context.prec = 50
        return numerator / denominator


def decimal_text(value):
    return format(value, ".9f")


def geometric_mean(values):
    if not values:
        return ""
    try:
        mean_log = sum(math.log(float(value)) for value in values) / len(values)
        result = math.exp(mean_log)
    except (OverflowError, ValueError):
        raise ReportError("speedup values are outside the supported aggregate range")
    if not math.isfinite(result) or result <= 0:
        raise ReportError("geometric-mean speedup is not finite and positive")
    return "{0:.9f}".format(result)


def diagnostic_log_path(result_root, status_row):
    family = status_row["family"]
    label = PurePosixPath(status_row["query"]).stem
    phase = status_row["phase"]
    logs = result_root / "logs"
    if phase.startswith("capture"):
        candidates = [logs / (family + "__" + label + "__capture.log")]
    elif phase.startswith("execute") or status_row["status"] == "PASS":
        candidates = [logs / (family + "__" + label + "__experiment.log")]
    elif phase == "provenance":
        candidates = [
            logs / (family + "__" + label + "__correctness_provenance.log")
        ]
    elif phase == "setup":
        candidates = [logs / "setup_pg.log"]
    elif phase == "prepare":
        candidates = [
            logs / ("prepare_pg_" + family + ".log"),
            logs / ("prepare_correctness_" + family + ".log"),
        ]
    else:
        candidates = []
    existing = next((path for path in candidates if path.is_file()), None)
    return str(existing.resolve()) if existing is not None else ""


def legacy_note(status, phase, correctness_evidence):
    if status == "PASS":
        return "OK"
    if correctness_evidence.get("correct") == "FALSE":
        return "NOT-EQUIV"
    if status == "SKIP" and "timeout" in phase:
        return "TIMEOUT"
    return "ERROR" if status == "FAIL" else status


def apply_legacy_oy_fields(output, values):
    for legacy_field, trace_field in LEGACY_OY_FIELD_MAP.items():
        output[legacy_field] = values.get(trace_field, "-")
    output["reorder"] = {
        "0": "No",
        "1": "Yes",
    }.get(output["outer_reordered"], "-")


def existing_artifact(path_text):
    if not path_text:
        return "-"
    path = Path(path_text)
    return str(path.resolve()) if path.is_file() else "-"


def build_comparison_rows(result_root, status_rows):
    comparison_rows = []
    seen = set()
    for status_row in status_rows:
        line_number = status_row["_line_number"]
        family = status_row["family"]
        query = status_row["query"]
        status = status_row["status"]
        if not family or not query:
            raise ReportError(
                "status.tsv:{0}: family and query must be non-empty".format(line_number)
            )
        identity = (family, query)
        if identity in seen:
            raise ReportError(
                "status.tsv:{0}: duplicate query identity {1}/{2}".format(
                    line_number, family, query
                )
            )
        seen.add(identity)
        if status not in ("PASS", "SKIP", "FAIL"):
            raise ReportError(
                "status.tsv:{0}: unsupported status {1!r}".format(line_number, status)
            )

        # Original columns use the original harness's '-' or NA conventions.
        # Additive columns use empty text only where no artifact exists.
        output = {field: "-" for field in ORIGINAL_CSV_FIELDS}
        output.update({field: "" for field in PGPLAN_CSV_FIELDS})
        output.update({field: "" for field in COMPARISON_CSV_FIELDS})
        label = PurePosixPath(query).stem
        correctness_evidence = {}
        output.update(
            {
                "query": label,
                "family": family,
                "sql_path": query,
                "correct": "NA",
                "effective_pass": "main",
                "kernel": "-",
                "kernel_detail": "-",
                "kernel_hash_reasons": "-",
                "t1_off": "NA",
                "t1_on": "NA",
                "t1_speedup": "NA",
                "t1_pgplan": "NA",
                "t1_native_vs_pgplan_speedup": "NA",
                "profile_round1_operator_s": "NA",
                "profile_round2_operator_s": "NA",
                "profile_round3_operator_s": "NA",
                "profile_round1_operator_count": "NA",
                "profile_round2_operator_count": "NA",
                "profile_round3_operator_count": "NA",
                "profile_total_time_s": "NA",
                "profile_round1_ratio": "NA",
                "profile_round2_ratio": "NA",
                "profile_total_sj_ratio": "NA",
                "profile_round3_ratio": "NA",
                "profile_other_elapsed_s": "NA",
                "profile_other_ratio": "NA",
                "profile_timed_samples": "NA",
                "profile_threads": "NA",
                "profile_cpu_time_s": "NA",
                "pgplan_plan": existing_artifact(status_row["plan"]),
                "pgplan_comparison_status": status,
                "pgplan_comparison_phase": status_row["phase"],
                "pgplan_comparison_detail": status_row["detail"],
                "pgplan_comparison_status_plan": status_row["plan"],
                "pgplan_comparison_result_dir": status_row["result_dir"],
                "pgplan_comparison_diagnostic_log": diagnostic_log_path(
                    result_root, status_row
                ),
                "_status": status,
                "_timeout_seconds": "",
            }
        )
        if status == "PASS":
            artifacts = read_pass_artifacts(result_root, status_row)
            medians = artifacts["medians"]
            pgplan_vs_native = speedup(medians["native"], medians["pgplan"])
            outer_yan_vs_native = speedup(
                medians["native"], medians["outer_yan"]
            )
            correctness_origin = artifacts["correctness_origin"]
            if correctness_origin in ("FRESH", "REUSED") or (
                not correctness_origin
                and artifacts["correctness_status"].startswith("PASS")
            ):
                correct_value = "TRUE"
                note_value = "OK"
            elif correctness_origin == "PARTIAL":
                correct_value = "PARTIAL"
                note_value = "PGPLAN-ONLY"
            else:
                correct_value = "NA"
                note_value = "NOT-CHECKED"
            output.update(
                {
                    "correct": correct_value,
                    "relation_count": artifacts["relation_count"],
                    "rows": artifacts["correctness_rows"],
                    "note": note_value,
                    "pgplan_status": "VERIFIED",
                    "pgplan_plan": artifacts["artifact_path"],
                    "pgplan_target_verification": artifacts[
                        "pgplan_target_verification"
                    ],
                    "pgplan_correctness_verification": artifacts[
                        "pgplan_correctness_verification"
                    ],
                    "tm_off": artifacts["median_text"]["native"],
                    "tm_pgplan": artifacts["median_text"]["pgplan"],
                    "tm_on": artifacts["median_text"]["outer_yan"],
                    "tm_speedup": decimal_text(outer_yan_vs_native),
                    "tm_native_vs_pgplan_speedup": decimal_text(pgplan_vs_native),
                    "pgplan_comparison_mode": artifacts["comparison_mode"],
                    "pgplan_correctness_comparison_set": artifacts[
                        "correctness_comparison_set"
                    ],
                    "pgplan_correctness_scope": artifacts[
                        "correctness_scope"
                    ],
                    "pgplan_correctness_status": artifacts[
                        "correctness_status"
                    ],
                    "pgplan_correctness_sha256": artifacts[
                        "correctness_sha256"
                    ],
                    "pgplan_correctness_hash_rows": artifacts[
                        "correctness_hash_rows"
                    ],
                    "pgplan_correctness_outer_yan_selected_plan": artifacts[
                        "correctness_outer_yan_selected_plan"
                    ],
                    "pgplan_correctness_origin": artifacts[
                        "correctness_origin"
                    ],
                    "pgplan_correctness_comparison_executed": artifacts[
                        "correctness_comparison_executed"
                    ],
                    "pgplan_correctness_reuse_source": artifacts[
                        "correctness_reuse_source"
                    ],
                    "pgplan_correctness_receipt_sha256": artifacts[
                        "correctness_receipt_sha256"
                    ],
                    "pgplan_correctness_reuse_source_receipt_sha256": artifacts[
                        "correctness_reuse_source_receipt_sha256"
                    ],
                    "pgplan_correctness_reuse_source_manifest_sha256": artifacts[
                        "correctness_reuse_source_manifest_sha256"
                    ],
                    "pgplan_comparison_measured_runs": artifacts["measured_runs"],
                    "pgplan_comparison_threads": artifacts["threads"],
                    "pgplan_comparison_result_dir": artifacts["run_dir"],
                    "pgplan_comparison_relations": artifacts["relations"],
                    "pgplan_comparison_join_count": artifacts["join_count"],
                    "_pgplan_speedup": pgplan_vs_native,
                    "_outer_yan_native_speedup": outer_yan_vs_native,
                    "_timeout_seconds": artifacts["timeout_seconds"],
                }
            )
            apply_legacy_oy_fields(output, artifacts["oy_values"])

            t1_medians = artifacts["t1_medians"]
            if t1_medians is not None:
                t1_pgplan_vs_native = speedup(
                    t1_medians["native"], t1_medians["pgplan"]
                )
                t1_outer_vs_native = speedup(
                    t1_medians["native"], t1_medians["outer_yan"]
                )
                output.update(
                    {
                        "t1_off": artifacts["t1_median_text"]["native"],
                        "t1_pgplan": artifacts["t1_median_text"]["pgplan"],
                        "t1_on": artifacts["t1_median_text"]["outer_yan"],
                        "t1_speedup": decimal_text(t1_outer_vs_native),
                        "t1_native_vs_pgplan_speedup": decimal_text(
                            t1_pgplan_vs_native
                        ),
                    }
                )

            run_dir = Path(artifacts["run_dir"])
            output["duckdb_plan"] = existing_artifact(
                str(run_dir / "plans" / "native.txt")
            )
            output["enabled_plan"] = existing_artifact(
                str(run_dir / "plans" / "outer_yan.txt")
            )
            output["trace_file"] = existing_artifact(
                str(run_dir / "traces" / "outer_yan_decision.trace")
            )
            target_pg = artifacts["pgplan_target"]
            correctness_pg = artifacts["pgplan_correctness"]
            for key in (
                "expected_semantic_signature",
                "final_semantic_signature",
                "implied_equality_count",
            ):
                output["pgplan_" + key] = target_pg.get(key, "")
                output["pgplan_correctness_" + key] = correctness_pg.get(
                    key, ""
                )
        else:
            correctness_evidence = read_nonpass_correctness(result_root, status_row)
            if correctness_evidence:
                output["correct"] = correctness_evidence.get("correct", "NA")
                output["pgplan_comparison_mode"] = correctness_evidence.get(
                    "comparison_mode", ""
                )
                output["pgplan_correctness_comparison_set"] = correctness_evidence.get(
                    "correctness_comparison_set", ""
                )
                output["rows"] = correctness_evidence.get(
                    "correctness_rows", "-"
                )
                output["pgplan_correctness_scope"] = correctness_evidence.get(
                    "correctness_scope", ""
                )
                output["pgplan_correctness_status"] = correctness_evidence.get(
                    "correctness_status", ""
                )
                output["pgplan_correctness_sha256"] = correctness_evidence.get(
                    "correctness_sha256", ""
                )
                output["pgplan_correctness_hash_rows"] = correctness_evidence.get(
                    "correctness_hash_rows", ""
                )
                output["pgplan_correctness_origin"] = correctness_evidence.get(
                    "correctness_origin", ""
                )
                output[
                    "pgplan_correctness_comparison_executed"
                ] = correctness_evidence.get(
                    "correctness_comparison_executed", ""
                )
                output[
                    "pgplan_correctness_reuse_source"
                ] = correctness_evidence.get("correctness_reuse_source", "")
                output[
                    "pgplan_correctness_receipt_sha256"
                ] = correctness_evidence.get("correctness_receipt_sha256", "")
                output[
                    "pgplan_correctness_reuse_source_receipt_sha256"
                ] = correctness_evidence.get(
                    "correctness_reuse_source_receipt_sha256", ""
                )
                output[
                    "pgplan_correctness_reuse_source_manifest_sha256"
                ] = correctness_evidence.get(
                    "correctness_reuse_source_manifest_sha256", ""
                )
                output["pgplan_comparison_result_dir"] = correctness_evidence.get(
                    "result_dir", output["pgplan_comparison_result_dir"]
                )
        output["note"] = legacy_note(status, status_row["phase"], correctness_evidence)
        comparison_rows.append(output)
    total = len(comparison_rows)
    for ordinal, output in enumerate(comparison_rows, start=1):
        output["pgplan_comparison_ordinal"] = str(ordinal)
        output["pgplan_comparison_total"] = str(total)
    return comparison_rows


def aggregate_row(family, rows):
    selected = [row for row in rows if family == "all" or row["family"] == family]
    passed = [row for row in selected if row["_status"] == "PASS"]
    pgplan_speedups = [row["_pgplan_speedup"] for row in passed]
    outer_native_speedups = [row["_outer_yan_native_speedup"] for row in passed]
    return {
        "family": family,
        "selected_queries": str(len(selected)),
        "pass_queries": str(len(passed)),
        "skip_queries": str(sum(row["_status"] == "SKIP" for row in selected)),
        "fail_queries": str(sum(row["_status"] == "FAIL" for row in selected)),
        "timed_queries": str(len(passed)),
        "pgplan_speedup_vs_native_geomean": geometric_mean(pgplan_speedups),
        "outer_yan_speedup_vs_native_geomean": geometric_mean(
            outer_native_speedups
        ),
        "pgplan_faster_than_native": str(sum(value > 1 for value in pgplan_speedups)),
        "outer_yan_faster_than_native": str(
            sum(value > 1 for value in outer_native_speedups)
        ),
    }


def render_table(fields, rows, delimiter):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=fields,
        delimiter=delimiter,
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def display(value, unavailable="NA"):
    return str(value) if value not in (None, "") else unavailable


def detail_value(value):
    text = display(value)
    if re.match(r"^[A-Za-z0-9_./:+()=|,-]+$", text):
        return text
    return json.dumps(text, ensure_ascii=True)


def render_comparison_block(row, index, total):
    main = (
        "[{0:3d}/{1}] {2:<36} correct={3} reorder={4} selected={5} "
        "comparison={6} PGPlan={7}  "
        "TM:[Original={8} PGPlan={9} OuterYan={10}] "
        "Speedup:[Original/PGPlan={11} Original/OuterYan={12}]  "
        "T1:[Original={13} PGPlan={14} OuterYan={15}] "
        "Speedup:[Original/PGPlan={16} Original/OuterYan={17}]"
    ).format(
        index,
        total,
        row["query"],
        row["correct"],
        display(row["outer_reordered"], "-"),
        display(row["selected_plan"], "-"),
        display(row["pgplan_comparison_mode"]),
        display(row["pgplan_status"]),
        display(row["tm_off"]),
        display(row["tm_pgplan"]),
        display(row["tm_on"]),
        display(row["tm_native_vs_pgplan_speedup"]),
        display(row["tm_speedup"]),
        display(row["t1_off"]),
        display(row["t1_pgplan"]),
        display(row["t1_on"]),
        display(row["t1_native_vs_pgplan_speedup"]),
        display(row["t1_speedup"]),
    )

    decision = (
        "[mode={0} reason={1} raw_winner={2} gate={3} gate_applied={4} "
        "proven_empty={5} outer_yan_selected={6} formula={7}]"
    ).format(
        display(row["selection_mode"]), display(row["decision_reason"]),
        display(row["raw_cost_winner"]), display(row["gate_result"]),
        display(row["cost_gate_applied"]),
        display(row["baseline_proven_empty"]),
        display(row["outer_yan_selected"]), display(row["formula_id"]),
    )
    risk = (
        "[default_filter_upper_checked={0} selected={1} retained={2} "
        "amplification={3} guard={4} full_reduction_bound={5} "
        "stretch_eligible={6} stretch_selected={7} join_input_ratio={8}]"
    ).format(
        display(row["default_filter_upper_bound_checked"]),
        display(row["default_filter_upper_bound_selected"]),
        display(row["semijoin_retained_cardinality_ratio"]),
        display(row["uncertain_filter_cardinality_amplification"]),
        display(row["uncertain_filter_amplification_guard"]),
        display(row["full_reduction_cardinality_lower_bound_applied"]),
        display(row["stretch_cost_gate_eligible"]),
        display(row["stretch_cost_gate_selected"]),
        display(row["candidate_to_baseline_join_input_ratio"]),
    )
    if row["candidate_total"] in ("", "-", "NA") or row["baseline_cost"] in (
        "", "-", "NA"
    ):
        cost = "[UNAVAILABLE]"
        gate = "[UNAVAILABLE]"
    else:
        cost = (
            "[OuterYan={0} + {1}*{2} = {3}; DuckDB={4}; delta={5}; "
            "raw_ratio={6}]"
        ).format(
            row["candidate_join_cost"], row["semijoin_cost_ratio"],
            row["semijoin_raw_cost"], row["candidate_total"],
            row["baseline_cost"], row["raw_cost_delta"], row["raw_cost_ratio"],
        )
        gate = (
            "[numeric:{0} <= {1} (= {2}*{3}); final={4}; margin={5}]"
        ).format(
            row["gate_lhs"], row["gate_rhs"], row["cost_ratio_limit"],
            row["baseline_cost"], row["gate_result"], row["gate_margin"],
        )
    semijoin = (
        "[R1(build={0} probe={1} pairs={2} filters={3}) "
        "R2(build={4} probe={5} pairs={6} filters={7}) weighted={8}]"
    ).format(
        display(row["round1_build"]), display(row["round1_probe"]),
        display(row["round1_pairs"]), display(row["round1_filters"]),
        display(row["round2_build"]), display(row["round2_probe"]),
        display(row["round2_pairs"]), display(row["round2_filters"]),
        display(row["weighted_semijoin_cost"]),
    )
    weights = (
        "[join(inner={0} unmatched_left={1} unmatched_right={2}) "
        "SJ(materialize={3} filter_build={4} replay={5} lookup={6} emit={7})]"
    ).format(
        display(row["inner_output_weight"]),
        display(row["unmatched_left_weight"]),
        display(row["unmatched_right_weight"]),
        display(row["semijoin_materialize_weight"]),
        display(row["semijoin_filter_build_weight"]),
        display(row["semijoin_replay_weight"]),
        display(row["semijoin_probe_lookup_weight"]),
        display(row["semijoin_probe_emit_weight"]),
    )
    pgplan = (
        "[target={0} correctness={1} implied_equalities={2} "
        "correctness_implied_equalities={3}]"
    ).format(
        display(row["pgplan_target_verification"]),
        display(row["pgplan_correctness_verification"]),
        display(row["pgplan_implied_equality_count"]),
        display(row["pgplan_correctness_implied_equality_count"]),
    )
    details = (
        "  details: family={0} sql={1} pass={2} timeout={3}s note={4} "
        "rows={5} nrel={6}"
    ).format(
        detail_value(row["family"]), detail_value(row["sql_path"]),
        row["effective_pass"], display(row.get("_timeout_seconds")),
        row["note"], display(row["rows"], "-"),
        display(row["relation_count"], "-"),
    )
    if row["_status"] == "PASS" and row["selected_plan"] in SELECTED_PLANS:
        details += (
            " decision={0} risk={1} cost={2} gate_cmp={3} SJ={4} weights={5}"
        ).format(decision, risk, cost, gate, semijoin, weights)
    else:
        details += " gate_detail=[{0}]".format(
            detail_value(row["pgplan_comparison_detail"])
        )
    details += (
        " pgplan={0} correctness=[mode={1} checked={2} scope={3} origin={4} "
        "status={5} sha256={6}] "
        "comparison=[status={7} phase={8} detail={9} runs={10} threads={11}] "
        "artifacts=[duckdb={12} enabled={13} trace={14} cost={15} "
        "pgplan={16} run={17} diagnostic_log={18}]"
    ).format(
        pgplan, display(row["pgplan_comparison_mode"]),
        display(row["pgplan_correctness_comparison_set"]),
        display(row["pgplan_correctness_scope"]),
        display(row["pgplan_correctness_origin"]),
        detail_value(row["pgplan_correctness_status"]),
        display(row["pgplan_correctness_sha256"]),
        row["pgplan_comparison_status"],
        detail_value(row["pgplan_comparison_phase"]),
        detail_value(row["pgplan_comparison_detail"]),
        display(row["pgplan_comparison_measured_runs"]),
        display(row["pgplan_comparison_threads"]), detail_value(row["duckdb_plan"]),
        detail_value(row["enabled_plan"]), detail_value(row["trace_file"]),
        detail_value(row["cost_file"]), detail_value(row["pgplan_plan"]),
        detail_value(row["pgplan_comparison_result_dir"]),
        detail_value(row["pgplan_comparison_diagnostic_log"]),
    )
    return "\n" + LOG_SEPARATOR + "\n" + main + "\n" + details + "\n"


def render_comparison_log(rows):
    total = len(rows)
    return "".join(
        render_comparison_block(row, index, total)
        for index, row in enumerate(rows, start=1)
    )


def atomic_write(path, content):
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".{0}.".format(path.name), dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_name, str(path))
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def generate_report(result_root):
    status_path = result_root / "status.tsv"
    status_rows = read_tsv(status_path, STATUS_FIELDS)
    if not status_rows:
        raise ReportError("{0}: contains no query rows".format(status_path))

    comparison_rows = build_comparison_rows(result_root, status_rows)
    family_order = []
    for row in comparison_rows:
        if row["family"] not in family_order:
            family_order.append(row["family"])
    summary_rows = [aggregate_row("all", comparison_rows)]
    summary_rows.extend(aggregate_row(family, comparison_rows) for family in family_order)
    failure_rows = [row for row in status_rows if row["status"] != "PASS"]

    outputs = {
        "comparison_tsv": result_root / "comparison.tsv",
        "comparison_csv": result_root / "comparison.csv",
        "comparison_log": result_root / "comparison.log",
        "summary_tsv": result_root / "summary.tsv",
        "failures_tsv": result_root / "failures.tsv",
    }
    rendered = {
        "comparison_tsv": render_table(COMPARISON_FIELDS, comparison_rows, "\t"),
        "comparison_csv": render_table(COMPARISON_FIELDS, comparison_rows, ","),
        "comparison_log": render_comparison_log(comparison_rows),
        "summary_tsv": render_table(SUMMARY_FIELDS, summary_rows, "\t"),
        "failures_tsv": render_table(STATUS_FIELDS, failure_rows, "\t"),
    }
    for name in (
        "comparison_tsv",
        "comparison_csv",
        "comparison_log",
        "summary_tsv",
        "failures_tsv",
    ):
        atomic_write(outputs[name], rendered[name])
    return outputs, summary_rows[0]


def main(argv=None):
    arguments = parse_args(argv)
    result_root = Path(arguments.result_dir)
    if not result_root.is_dir():
        print(
            "summarize_corpus.py: result directory does not exist: {0}".format(
                result_root
            ),
            file=sys.stderr,
        )
        return 2
    result_root = result_root.resolve()
    try:
        if arguments.print_row is not None:
            status_rows = read_tsv(result_root / "status.tsv", STATUS_FIELDS)
            if arguments.print_row > len(status_rows):
                raise ReportError(
                    "--print-row {0} exceeds the {1} current status rows".format(
                        arguments.print_row, len(status_rows)
                    )
                )
            comparison_row = build_comparison_rows(
                result_root, [status_rows[arguments.print_row - 1]]
            )[0]
            sys.stdout.write(
                render_comparison_block(
                    comparison_row, arguments.print_row, arguments.total
                )
            )
            return 0
        outputs, totals = generate_report(result_root)
    except ReportError as error:
        print("summarize_corpus.py: {0}".format(error), file=sys.stderr)
        return 2
    except OSError as error:
        print("summarize_corpus.py: cannot write report: {0}".format(error), file=sys.stderr)
        return 2

    print(
        "[comparison] selected={0} pass={1} skip={2} fail={3}".format(
            totals["selected_queries"],
            totals["pass_queries"],
            totals["skip_queries"],
            totals["fail_queries"],
        )
    )
    print(
        "[comparison] geometric-mean speedup over {0} timed queries "
        "(>1 means the named candidate is faster): "
        "pgplan_vs_original={1} outer_yan_vs_original={2}".format(
            totals["timed_queries"],
            totals["pgplan_speedup_vs_native_geomean"] or "n/a",
            totals["outer_yan_speedup_vs_native_geomean"] or "n/a",
        )
    )
    for name in (
        "comparison_tsv",
        "comparison_csv",
        "comparison_log",
        "summary_tsv",
        "failures_tsv",
    ):
        print("[comparison] {0}={1}".format(name, outputs[name]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
