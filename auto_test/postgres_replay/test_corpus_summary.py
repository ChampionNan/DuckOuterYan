#!/usr/bin/env python3
"""Focused tests for the aggregate DuckDB/PGPlan/OuterYan corpus report."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
SUMMARIZER = SCRIPT_DIR / "summarize_corpus.py"
CANONICAL_WRAPPER = SCRIPT_DIR.parent / "pgplan" / "summarize_corpus.sh"
ORIGINAL_HARNESS = SCRIPT_DIR.parent / "experiment_onoff.sh"
STATUS_FIELDS = (
    "family",
    "query",
    "status",
    "phase",
    "detail",
    "plan",
    "result_dir",
)
PGPLAN_FIELDS = (
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
COMPARISON_FIELDS = (
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


def write_tsv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def original_csv_fields() -> tuple[str, ...]:
    source = ORIGINAL_HARNESS.read_text(encoding="utf-8")
    match = re.search(r"CSV_HEADER=\(\n(.*?)\n\)", source, re.DOTALL)
    if match is None:
        raise AssertionError("could not find experiment_onoff.sh CSV_HEADER")
    return tuple(match.group(1).split())


class CorpusSummaryTest(unittest.TestCase):
    @staticmethod
    def pgplan_trace(signature: str) -> str:
        imported = {
            "event": "imported",
            "query_sha256_verified": True,
            "artifact_raw_signature": "J[inner](S:left,S:right)",
            "imported_raw_signature": "J[inner](S:left,S:right)",
            "implied_equality_count": 2,
            "expected_semantic_signature": signature,
        }
        verified = {
            "event": "verified",
            "expected_semantic_signature": signature,
            "final_semantic_signature": signature,
        }
        return "[PGPLAN] {0}\n[PGPLAN] {1}\n".format(
            json.dumps(imported, separators=(",", ":")),
            json.dumps(verified, separators=(",", ":")),
        )

    @staticmethod
    def oy_trace(selected_plan: str) -> str:
        selected = "1" if selected_plan == "OUTERYAN" else "0"
        reordered = selected
        return (
            "[OY_DECISION] formula_id=OUTER_YAN_COST_V6 selection_mode=GATED "
            "default_filter_upper_bound_checked=1 "
            "default_filter_upper_bound_selected=0 "
            "full_reduction_cardinality_lower_bound_applied=0 "
            "uncertain_filter_amplification_guard=0 stretch_cost_gate_eligible=1 "
            "stretch_cost_gate_selected={selected} selected_plan={plan} "
            "outer_reordered={reordered} cost_gate_applied=1 "
            "outer_yan_selected={selected} baseline_proven_empty=0 "
            "reason=COST_{plan}_BETTER raw_cost_winner={plan} gate_result=PASS "
            "baseline_cost=100 baseline_join_input_rows=90 candidate_join_input_rows=40 "
            "candidate_to_baseline_join_input_ratio=0.444 "
            "semijoin_retained_cardinality_ratio=0.5 "
            "uncertain_filter_cardinality_amplification=0 candidate_join_cost=40 "
            "semijoin_raw_cost=20 semijoin_cost_ratio=0.5 "
            "weighted_semijoin_cost=10 candidate_total=50 cost_ratio_limit=1 "
            "baseline_threshold=100 round1_build=8 round1_probe=7 round2_build=6 "
            "round2_probe=5 round1_pairs=2 round1_filters=2 round2_pairs=1 "
            "round2_filters=1 raw_cost_delta=-50 raw_cost_ratio=0.5 gate_lhs=50 "
            "gate_rhs=100 gate_margin=50 inner_output_weight=1 unmatched_left_weight=1 "
            "unmatched_right_weight=1 semijoin_materialize_weight=1 "
            "semijoin_filter_build_weight=1 semijoin_replay_weight=1 "
            "semijoin_probe_lookup_weight=1 semijoin_probe_emit_weight=1\n"
        ).format(selected=selected, plan=selected_plan, reordered=reordered)

    def create_run(
        self,
        root: Path,
        family: str,
        query: str,
        medians: tuple[str, str, str] = ("10", "5", "2"),
        runs: tuple[str, str, str] = ("3", "3", "3"),
        threads: tuple[str, str, str] = ("8", "8", "8"),
        configurations: tuple[str, ...] = ("native", "pgplan", "outer_yan"),
        target_plan: str = "OUTERYAN",
        correctness_plan: str = "DUCKDB",
        include_correctness: bool = True,
        include_correctness_plan: bool = True,
        t1_medians: tuple[str, str, str] | None = None,
        correctness_provenance: dict[str, str] | None = None,
        correctness_db: str = "/data/bounded.duckdb",
    ) -> Path:
        label = Path(query).stem
        run_dir = root / "runs" / family / label
        timing_rows = []
        for index, configuration in enumerate(configurations):
            timing_rows.append(
                {
                    "configuration": configuration,
                    "median_seconds": medians[index],
                    "measured_runs": runs[index],
                    "threads": threads[index],
                }
            )
        write_tsv(
            run_dir / "timing" / "summary.tsv",
            ("configuration", "median_seconds", "measured_runs", "threads"),
            timing_rows,
        )
        if t1_medians is not None:
            write_tsv(
                run_dir / "timing" / "t1_summary.tsv",
                ("configuration", "median_seconds", "measured_runs", "threads"),
                [
                    {
                        "configuration": configuration,
                        "median_seconds": t1_medians[index],
                        "measured_runs": "1",
                        "threads": "1",
                    }
                    for index, configuration in enumerate(configurations)
                ],
            )
        provenance = run_dir / "provenance" / "manifest.txt"
        provenance.parent.mkdir(parents=True, exist_ok=True)
        manifest = (
            "execution_db=/data/target.duckdb\n"
            "timeout_seconds=1800\n"
            "outer_yan_selected_plan={0}\n"
        ).format(target_plan)
        if include_correctness_plan:
            manifest += "correctness_db={0}\n".format(correctness_db)
            manifest += "correctness_outer_yan_selected_plan={0}\n".format(
                correctness_plan
            )
        if correctness_provenance:
            manifest += "".join(
                "{0}={1}\n".format(key, value)
                for key, value in correctness_provenance.items()
            )
        provenance.write_text(manifest, encoding="utf-8")
        artifact = {
            "format": "duckyan.pg_join_tree.v1",
            "tree": {
                "op": "join",
                "join_type": "inner",
                "left": {
                    "op": "scan",
                    "schema": "public",
                    "relation": "left table",
                    "alias": "left alias",
                },
                "right": {
                    "op": "scan",
                    "schema": "public",
                    "relation": "right_table",
                    "alias": "r",
                },
            },
        }
        (run_dir / "provenance" / "postgres_plan.json").write_text(
            json.dumps(artifact), encoding="utf-8"
        )
        traces = run_dir / "traces"
        traces.mkdir(parents=True, exist_ok=True)
        signature = "I(S:left,S:right)"
        (traces / "pgplan_explain.trace").write_text(
            self.pgplan_trace(signature), encoding="utf-8"
        )
        (traces / "outer_yan_decision.trace").write_text(
            self.oy_trace(target_plan), encoding="utf-8"
        )
        if include_correctness_plan:
            (traces / "pgplan_correctness.trace").write_text(
                self.pgplan_trace(signature), encoding="utf-8"
            )
            (traces / "outer_yan_correctness_decision.trace").write_text(
                self.oy_trace(correctness_plan), encoding="utf-8"
            )
        if include_correctness:
            write_tsv(
                run_dir / "correctness" / "row_counts.tsv",
                ("configuration", "rows"),
                [
                    {"configuration": configuration, "rows": "42"}
                    for configuration in ("native", "pgplan", "outer_yan")
                ],
            )
            (run_dir / "correctness" / "status.txt").write_text(
                "PASS: exact bounded multisets are identical\n", encoding="utf-8"
            )
            write_tsv(
                run_dir / "correctness" / "multiset_sha256.tsv",
                ("sha256", "rows"),
                [{"sha256": "a" * 64, "rows": "42"}],
            )
        return run_dir

    def run_summarizer(
        self,
        root: Path,
        wrapper: bool = False,
        print_row: int | None = None,
        total: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = (
            [str(CANONICAL_WRAPPER), "--result-dir", str(root)]
            if wrapper
            else [sys.executable, str(SUMMARIZER), "--result-dir", str(root)]
        )
        if print_row is not None:
            command.extend(["--print-row", str(print_row), "--total", str(total)])
        env = os.environ.copy()
        env["PYTHON_BIN"] = sys.executable
        return subprocess.run(command, text=True, capture_output=True, check=False, env=env)

    def write_status(self, root: Path, rows: list[dict[str, str]]) -> None:
        write_tsv(root / "status.tsv", STATUS_FIELDS, rows)

    @staticmethod
    def status_row(
        family: str,
        query: str,
        status: str,
        result_dir: str = "",
        phase: str = "complete",
        detail: str = "complete",
    ) -> dict[str, str]:
        return {
            "family": family,
            "query": query,
            "status": status,
            "phase": phase,
            "detail": detail,
            "plan": "/plans/{0}.json".format(Path(query).stem) if status != "SKIP" else "",
            "result_dir": result_dir,
        }

    def test_mixed_corpus_outputs_ordered_comparison_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph_run = self.create_run(root, "graph", "graph/a.sql")
            tpch_run = self.create_run(
                root,
                "tpch",
                "tpch/b.sql",
                medians=("8.000000000", "16.000000000", "4.000000000"),
                include_correctness=False,
                include_correctness_plan=False,
            )
            missing_machine_root = "/old/server/pgplan_corpus/runs/graph/a"
            self.write_status(
                root,
                [
                    self.status_row("graph", "graph/a.sql", "PASS", missing_machine_root),
                    self.status_row("job", "job/c.sql", "FAIL", phase="execute", detail="bad, result"),
                    self.status_row("tpch", "tpch/b.sql", "PASS", str(tpch_run)),
                    self.status_row("tpcds", "tpcds/d.sql", "SKIP", phase="capture_timeout", detail="300s"),
                ],
            )

            result = self.run_summarizer(root, wrapper=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[comparison] selected=4 pass=2 skip=1 fail=1", result.stdout)
            self.assertIn(
                "geometric-mean speedup over 2 timed queries", result.stdout
            )
            self.assertIn("pgplan_vs_original=1.000000000", result.stdout)
            self.assertIn("outer_yan_vs_original=3.162277660", result.stdout)

            comparison = read_tsv(root / "comparison.tsv")
            self.assertEqual(
                [
                    (row["family"], row["sql_path"], row["pgplan_comparison_status"])
                    for row in comparison
                ],
                [
                    ("graph", "graph/a.sql", "PASS"),
                    ("job", "job/c.sql", "FAIL"),
                    ("tpch", "tpch/b.sql", "PASS"),
                    ("tpcds", "tpcds/d.sql", "SKIP"),
                ],
            )
            self.assertEqual(comparison[0]["query"], "a")
            self.assertEqual(comparison[0]["tm_off"], "10")
            self.assertEqual(
                comparison[0]["tm_native_vs_pgplan_speedup"], "2.000000000"
            )
            self.assertEqual(comparison[0]["tm_speedup"], "5.000000000")
            self.assertEqual(comparison[0]["rows"], "42")
            self.assertEqual(
                comparison[0]["pgplan_comparison_result_dir"], str(graph_run.resolve())
            )
            self.assertEqual(comparison[1]["tm_off"], "-")
            self.assertEqual(comparison[2]["rows"], "")

            with (root / "comparison.csv").open(encoding="utf-8", newline="") as source:
                csv_rows = list(csv.DictReader(source))
                source.seek(0)
                csv_header = tuple(next(csv.reader(source)))
                self.assertEqual(
                    csv_header[: len(original_csv_fields())],
                    original_csv_fields(),
                )
            self.assertEqual(csv_rows[1]["pgplan_comparison_detail"], "bad, result")

            summary = read_tsv(root / "summary.tsv")
            self.assertEqual([row["family"] for row in summary], ["all", "graph", "job", "tpch", "tpcds"])
            self.assertEqual(summary[0]["selected_queries"], "4")
            self.assertEqual(summary[0]["pass_queries"], "2")
            self.assertEqual(summary[0]["skip_queries"], "1")
            self.assertEqual(summary[0]["fail_queries"], "1")
            self.assertEqual(summary[0]["pgplan_speedup_vs_native_geomean"], "1.000000000")
            self.assertEqual(summary[0]["outer_yan_speedup_vs_native_geomean"], "3.162277660")

            failures = read_tsv(root / "failures.tsv")
            self.assertEqual([row["status"] for row in failures], ["FAIL", "SKIP"])

    def test_invalid_pass_artifact_preserves_existing_reports(self) -> None:
        cases = {
            "missing configuration": {"configurations": ("native", "pgplan")},
            "non-positive median": {"medians": ("10", "0", "2")},
            "mismatched runs": {"runs": ("3", "5", "3")},
            "mismatched threads": {"threads": ("8", "4", "8")},
            "invalid target selected plan": {"target_plan": "PGPLAN"},
            "invalid correctness selected plan": {"correctness_plan": "PGPLAN"},
        }
        for name, options in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                run_dir = self.create_run(root, "graph", "graph/a.sql", **options)
                self.write_status(
                    root,
                    [self.status_row("graph", "graph/a.sql", "PASS", str(run_dir))],
                )
                for output_name in (
                    "comparison.tsv",
                    "comparison.csv",
                    "comparison.log",
                    "summary.tsv",
                    "failures.tsv",
                ):
                    (root / output_name).write_text("old-report\n", encoding="utf-8")

                result = self.run_summarizer(root)
                self.assertEqual(result.returncode, 2)
                for output_name in (
                    "comparison.tsv",
                    "comparison.csv",
                    "comparison.log",
                    "summary.tsv",
                    "failures.tsv",
                ):
                    self.assertEqual(
                        (root / output_name).read_text(encoding="utf-8"),
                        "old-report\n",
                    )

    def test_correctness_counts_are_strict_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self.create_run(root, "graph", "graph/a.sql")
            write_tsv(
                run_dir / "correctness" / "row_counts.tsv",
                ("configuration", "rows"),
                [
                    {"configuration": "native", "rows": "42"},
                    {"configuration": "pgplan", "rows": "41"},
                    {"configuration": "outer_yan", "rows": "42"},
                ],
            )
            self.write_status(
                root,
                [self.status_row("graph", "graph/a.sql", "PASS", str(run_dir))],
            )
            result = self.run_summarizer(root)
            self.assertEqual(result.returncode, 2)
            self.assertIn("correctness row counts differ", result.stderr)

    def test_legacy_run_without_correctness_selected_plan_is_reportable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self.create_run(
                root,
                "graph",
                "graph/a.sql",
                include_correctness_plan=False,
            )
            self.write_status(
                root,
                [self.status_row("graph", "graph/a.sql", "PASS", str(run_dir))],
            )

            result = self.run_summarizer(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            comparison = read_tsv(root / "comparison.tsv")
            self.assertEqual(comparison[0]["selected_plan"], "OUTERYAN")
            self.assertEqual(
                comparison[0]["pgplan_correctness_outer_yan_selected_plan"], ""
            )
            self.assertEqual(
                comparison[0]["pgplan_correctness_scope"], "target"
            )
            self.assertEqual(comparison[0]["pgplan_correctness_origin"], "")
            self.assertEqual(
                comparison[0]["pgplan_correctness_comparison_executed"], ""
            )
            log_text = (root / "comparison.log").read_text(encoding="utf-8")
            self.assertIn(
                "correctness=[mode=NA checked=NA scope=target origin=NA",
                log_text,
            )

    def test_fresh_correctness_provenance_is_explicit_in_csv_and_log(self) -> None:
        for scope, correctness_db in (
            ("target", "/data/target.duckdb"),
            ("bounded", "/data/bounded.duckdb"),
        ):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                run_dir = self.create_run(
                    root,
                    "graph",
                    "graph/a.sql",
                    correctness_db=correctness_db,
                    correctness_provenance={
                        "correctness_origin": "FRESH",
                        "correctness_comparison_executed": "1",
                        "correctness_scope": scope,
                        "correctness_receipt_sha256": "B" * 64,
                    },
                )
                self.write_status(
                    root,
                    [self.status_row("graph", "graph/a.sql", "PASS", str(run_dir))],
                )

                result = self.run_summarizer(root)
                self.assertEqual(result.returncode, 0, result.stderr)
                row = read_tsv(root / "comparison.tsv")[0]
                self.assertEqual(row["pgplan_correctness_scope"], scope)
                self.assertEqual(row["pgplan_correctness_origin"], "FRESH")
                self.assertEqual(
                    row["pgplan_correctness_comparison_executed"], "1"
                )
                self.assertEqual(row["pgplan_correctness_reuse_source"], "")
                self.assertEqual(
                    row["pgplan_correctness_receipt_sha256"], "b" * 64
                )
                log_text = (root / "comparison.log").read_text(encoding="utf-8")
                self.assertIn(
                    "correctness=[mode=both checked=both scope={0} "
                    "origin=FRESH".format(scope),
                    log_text,
                )

    def test_reused_correctness_reports_source_and_receipt_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reuse_source = "/prior corpus/runs/graph/a"
            run_dir = self.create_run(
                root,
                "graph",
                "graph/a.sql",
                correctness_db="/data/target.duckdb",
                correctness_provenance={
                    "correctness_origin": "REUSED",
                    "correctness_comparison_executed": "0",
                    "correctness_scope": "target",
                    "correctness_reuse_source": reuse_source,
                    "correctness_receipt_sha256": "C" * 64,
                    "correctness_reuse_source_receipt_sha256": "C" * 64,
                    "correctness_reuse_source_manifest_sha256": "E" * 64,
                },
            )
            self.write_status(
                root,
                [self.status_row("graph", "graph/a.sql", "PASS", str(run_dir))],
            )

            result = self.run_summarizer(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            with (root / "comparison.csv").open(
                encoding="utf-8", newline=""
            ) as source:
                reader = csv.DictReader(source)
                row = next(reader)
                header = tuple(reader.fieldnames or ())
            self.assertEqual(header[-len(COMPARISON_FIELDS):], COMPARISON_FIELDS)
            self.assertEqual(len(original_csv_fields()), 88)
            self.assertEqual(
                header[:len(original_csv_fields())], original_csv_fields()
            )
            pgplan_start = len(original_csv_fields())
            self.assertEqual(
                header[pgplan_start:pgplan_start + len(PGPLAN_FIELDS)],
                PGPLAN_FIELDS,
            )
            self.assertFalse(any("three_way" in field for field in header))
            for redundant_field in (
                "kernel_status",
                "profile_status",
                "t1_status",
                "outer_yan_decision_raw",
            ):
                self.assertNotIn(redundant_field, header)
            self.assertEqual(row["pgplan_correctness_origin"], "REUSED")
            self.assertEqual(
                row["pgplan_correctness_comparison_executed"], "0"
            )
            self.assertEqual(
                row["pgplan_correctness_reuse_source"], reuse_source
            )
            self.assertEqual(
                row["pgplan_correctness_receipt_sha256"], "c" * 64
            )
            self.assertEqual(
                row["pgplan_correctness_reuse_source_receipt_sha256"],
                "c" * 64,
            )
            self.assertEqual(
                row["pgplan_correctness_reuse_source_manifest_sha256"],
                "e" * 64,
            )
            log_text = (root / "comparison.log").read_text(encoding="utf-8")
            self.assertIn(
                "correctness=[mode=both checked=none scope=target "
                "origin=REUSED",
                log_text,
            )
            self.assertNotIn("source_receipt_sha256", log_text)
            self.assertNotIn("source_manifest_sha256", log_text)
            self.assertNotIn("origin=FRESH", log_text)

    def test_pgplan_only_reports_partial_correctness_from_two_configurations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self.create_run(
                root,
                "graph",
                "graph/a.sql",
                include_correctness=False,
                include_correctness_plan=False,
                correctness_provenance={
                    "comparison_mode": "pgplan-only",
                    "correctness_origin": "PARTIAL",
                    "correctness_comparison_executed": "1",
                    "correctness_comparison_set": "pgplan-only",
                    "correctness_status": "PARTIAL",
                    "correctness_scope": "bounded",
                },
            )
            write_tsv(
                run_dir / "correctness" / "row_counts.tsv",
                ("configuration", "rows"),
                [
                    {"configuration": "native", "rows": "42"},
                    {"configuration": "pgplan", "rows": "42"},
                ],
            )
            (run_dir / "correctness" / "status.txt").write_text(
                "PARTIAL: Original and PGPlan exact multisets are identical\n",
                encoding="utf-8",
            )
            write_tsv(
                run_dir / "correctness" / "multiset_sha256.tsv",
                ("sha256", "rows"),
                [{"sha256": "d" * 64, "rows": "42"}],
            )
            (run_dir / "traces" / "pgplan_correctness.trace").write_text(
                self.pgplan_trace("I(S:left,S:right)"), encoding="utf-8"
            )
            self.write_status(
                root,
                [self.status_row("graph", "graph/a.sql", "PASS", str(run_dir))],
            )

            result = self.run_summarizer(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            row = read_tsv(root / "comparison.tsv")[0]
            self.assertEqual(row["correct"], "PARTIAL")
            self.assertEqual(row["rows"], "42")
            self.assertEqual(row["pgplan_comparison_mode"], "pgplan-only")
            self.assertEqual(
                row["pgplan_correctness_comparison_set"], "pgplan-only"
            )
            self.assertEqual(row["pgplan_correctness_origin"], "PARTIAL")
            self.assertEqual(row["pgplan_correctness_comparison_executed"], "1")
            self.assertEqual(row["tm_off"], "10")
            self.assertEqual(row["tm_pgplan"], "5")
            self.assertEqual(row["tm_on"], "2")
            log_text = (root / "comparison.log").read_text(encoding="utf-8")
            self.assertIn("correct=PARTIAL", log_text)
            self.assertIn("comparison=pgplan-only", log_text)
            self.assertIn("checked=pgplan-only", log_text)
            self.assertNotIn("kernel=", log_text)
            self.assertNotIn("profile=[", log_text)
            self.assertNotIn("artifact_raw", log_text)
            self.assertNotIn("semantic_signature", log_text)

    def test_none_mode_reports_not_run_correctness_and_keeps_performance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self.create_run(
                root,
                "graph",
                "graph/a.sql",
                include_correctness=False,
                include_correctness_plan=False,
                correctness_provenance={
                    "comparison_mode": "none",
                    "correctness_origin": "NOT_RUN",
                    "correctness_comparison_executed": "0",
                    "correctness_comparison_set": "none",
                    "correctness_status": "NOT_RUN",
                    "correctness_scope": "not-run",
                },
            )
            self.write_status(
                root,
                [self.status_row("graph", "graph/a.sql", "PASS", str(run_dir))],
            )

            result = self.run_summarizer(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            row = read_tsv(root / "comparison.tsv")[0]
            self.assertEqual(row["correct"], "NA")
            self.assertEqual(row["rows"], "")
            self.assertEqual(row["pgplan_comparison_mode"], "none")
            self.assertEqual(row["pgplan_correctness_comparison_set"], "none")
            self.assertEqual(row["pgplan_correctness_scope"], "not-run")
            self.assertEqual(row["pgplan_correctness_origin"], "NOT_RUN")
            self.assertEqual(row["pgplan_correctness_comparison_executed"], "0")
            self.assertEqual(row["tm_off"], "10")
            self.assertEqual(row["tm_pgplan"], "5")
            self.assertEqual(row["tm_on"], "2")
            self.assertFalse((run_dir / "correctness").exists())
            log_text = (root / "comparison.log").read_text(encoding="utf-8")
            self.assertIn("correct=NA", log_text)
            self.assertIn("comparison=none", log_text)
            self.assertIn("checked=none scope=not-run origin=NOT_RUN", log_text)
            self.assertIn(
                "TM:[Original=10 PGPlan=5 OuterYan=2]", log_text
            )

    def test_inconsistent_explicit_correctness_provenance_is_rejected(self) -> None:
        cases = (
            (
                "wrong comparison flag",
                {
                    "correctness_origin": "REUSED",
                    "correctness_comparison_executed": "1",
                    "correctness_receipt_sha256": "a" * 64,
                },
                "correctness_comparison_executed must be 0 for REUSED",
            ),
            (
                "fresh with reuse source",
                {
                    "correctness_origin": "FRESH",
                    "correctness_comparison_executed": "1",
                    "correctness_receipt_sha256": "a" * 64,
                    "correctness_reuse_source": "/misleading/source",
                },
                "non-reused correctness must not contain reuse provenance",
            ),
            (
                "reused receipt mismatch",
                {
                    "correctness_origin": "REUSED",
                    "correctness_comparison_executed": "0",
                    "correctness_receipt_sha256": "a" * 64,
                    "correctness_reuse_source": "/prior/run",
                    "correctness_reuse_source_receipt_sha256": "b" * 64,
                    "correctness_reuse_source_manifest_sha256": "c" * 64,
                },
                "receipt/source receipt SHA-256 values differ",
            ),
        )
        for name, provenance, expected_error in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                run_dir = self.create_run(
                    root,
                    "graph",
                    "graph/a.sql",
                    correctness_provenance=provenance,
                )
                self.write_status(
                    root,
                    [
                        self.status_row(
                            "graph", "graph/a.sql", "PASS", str(run_dir)
                        )
                    ],
                )

                result = self.run_summarizer(root)
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected_error, result.stderr)

    def test_non_pass_rows_do_not_require_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_status(
                root,
                [
                    self.status_row("graph", "graph/a.sql", "FAIL", phase="capture"),
                    self.status_row("tpch", "tpch/b.sql", "SKIP", phase="capture_timeout"),
                ],
            )
            result = self.run_summarizer(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            comparison = read_tsv(root / "comparison.tsv")
            self.assertTrue(
                all(
                    row["pgplan_comparison_measured_runs"] == ""
                    for row in comparison
                )
            )
            summary = read_tsv(root / "summary.tsv")
            self.assertEqual(summary[0]["timed_queries"], "0")
            self.assertEqual(summary[0]["pgplan_speedup_vs_native_geomean"], "")

    def test_legacy_style_log_and_csv_have_duckdb_outeryan_fail_skip_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            quoted_query = 'graph family/outer "quoted" plan.sql'
            outer_run = self.create_run(
                root, "graph family", quoted_query, target_plan="OUTERYAN"
            )
            duck_run = self.create_run(
                root, "tpch", "tpch/duck.sql", target_plan="DUCKDB"
            )
            logs = root / "logs"
            logs.mkdir(parents=True)
            outer_log = logs / 'graph family__outer "quoted" plan__experiment.log'
            outer_log.write_text("experiment details\n", encoding="utf-8")
            self.write_status(
                root,
                [
                    self.status_row(
                        "graph family", quoted_query, "PASS", str(outer_run),
                        detail='complete with spaces and "quotes"',
                    ),
                    self.status_row("tpch", "tpch/duck.sql", "PASS", str(duck_run)),
                    self.status_row(
                        "job", "job/fail.sql", "FAIL", phase="execute target",
                        detail='failed with "quoted reason", then stopped',
                    ),
                    self.status_row(
                        "tpcds", "tpcds/skip.sql", "SKIP",
                        phase="capture_timeout", detail="300 seconds",
                    ),
                ],
            )

            result = self.run_summarizer(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            log_text = (root / "comparison.log").read_text(encoding="utf-8")
            self.assertEqual(log_text.count("=" * 100), 4)
            nonblank_lines = [line for line in log_text.splitlines() if line]
            self.assertEqual(len(nonblank_lines), 12)
            self.assertTrue(all(nonblank_lines[index] == "=" * 100 for index in range(0, 12, 3)))
            expected_outer_main = (
                '[  1/4] outer "quoted" plan'
                '                  correct=TRUE reorder=1 selected=OUTERYAN '
                'comparison=NA PGPlan=VERIFIED  '
                'TM:[Original=10 PGPlan=5 OuterYan=2] '
                'Speedup:[Original/PGPlan=2.000000000 '
                'Original/OuterYan=5.000000000]  '
                'T1:[Original=NA PGPlan=NA OuterYan=NA] '
                'Speedup:[Original/PGPlan=NA Original/OuterYan=NA]'
            )
            self.assertEqual(nonblank_lines[1], expected_outer_main)
            self.assertIn(
                "[  2/4] duck                                 correct=TRUE "
                "reorder=0 selected=DUCKDB",
                log_text,
            )
            self.assertIn(
                "[  3/4] fail                                 correct=NA "
                "reorder=- selected=-",
                log_text,
            )
            self.assertIn(
                "[  4/4] skip                                 correct=NA "
                "reorder=- selected=-",
                log_text,
            )
            self.assertIn('detail="complete with spaces and \\"quotes\\""', log_text)
            self.assertIn("nrel=2", log_text)
            self.assertIn("runs=3 threads=8", log_text)
            self.assertIn("target=VERIFIED correctness=VERIFIED", log_text)
            self.assertIn("implied_equalities=2", log_text)
            self.assertIn("decision=[mode=GATED", log_text)
            self.assertIn("SJ=[R1(build=8 probe=7 pairs=2 filters=2)", log_text)

            with (root / "comparison.csv").open(encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))
            outer = rows[0]
            self.assertEqual(outer["tm_off"], "10")
            self.assertEqual(outer["tm_pgplan"], "5")
            self.assertEqual(outer["tm_on"], "2")
            self.assertEqual(outer["tm_speedup"], "5.000000000")
            self.assertEqual(outer["correct"], "TRUE")
            self.assertEqual(outer["pgplan_correctness_scope"], "bounded")
            self.assertEqual(outer["pgplan_status"], "VERIFIED")
            self.assertEqual(outer["pgplan_implied_equality_count"], "2")
            self.assertEqual(outer["relation_count"], "2")
            self.assertEqual(outer["pgplan_comparison_join_count"], "1")
            self.assertEqual(outer["reorder"], "Yes")
            self.assertEqual(outer["outer_reordered"], "1")
            self.assertEqual(outer["selected_plan"], "OUTERYAN")
            self.assertEqual(outer["pgplan_comparison_ordinal"], "1")
            self.assertEqual(outer["pgplan_comparison_total"], "4")
            self.assertNotIn("kernel_status", outer)
            self.assertNotIn("profile_status", outer)
            self.assertNotIn("t1_status", outer)
            self.assertEqual(outer["t1_off"], "NA")
            self.assertEqual(outer["selection_mode"], "GATED")
            self.assertEqual(
                outer["pgplan_comparison_diagnostic_log"], str(outer_log.resolve())
            )
            self.assertNotIn("outer_yan_decision_raw", outer)
            self.assertFalse(any("artifact_raw" in field for field in outer))
            self.assertFalse(any("imported_raw" in field for field in outer))

    def test_real_t1_summary_populates_legacy_and_pgplan_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self.create_run(
                root,
                "graph",
                "graph/a.sql",
                t1_medians=("12", "6", "3"),
            )
            self.write_status(
                root,
                [self.status_row("graph", "graph/a.sql", "PASS", str(run_dir))],
            )

            result = self.run_summarizer(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            row = read_tsv(root / "comparison.tsv")[0]
            self.assertEqual(row["t1_off"], "12")
            self.assertEqual(row["t1_pgplan"], "6")
            self.assertEqual(row["t1_on"], "3")
            self.assertEqual(row["t1_speedup"], "4.000000000")
            self.assertEqual(
                row["t1_native_vs_pgplan_speedup"], "2.000000000"
            )
            self.assertNotIn("t1_status", row)
            # The comparison run-count field continues to describe TM;
            # the T1 artifact has its fixed one-measurement contract.
            self.assertEqual(row["pgplan_comparison_measured_runs"], "3")
            log_text = (root / "comparison.log").read_text(encoding="utf-8")
            self.assertIn(
                "T1:[Original=12 PGPlan=6 OuterYan=3]", log_text
            )
            self.assertIn(
                "Speedup:[Original/PGPlan=2.000000000 "
                "Original/OuterYan=4.000000000]",
                log_text,
            )

    def test_invalid_t1_summary_is_rejected_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self.create_run(
                root,
                "graph",
                "graph/a.sql",
                t1_medians=("12", "6", "3"),
            )
            t1_path = run_dir / "timing" / "t1_summary.tsv"
            rows = read_tsv(t1_path)
            rows[1]["threads"] = "2"
            write_tsv(
                t1_path,
                ("configuration", "median_seconds", "measured_runs", "threads"),
                rows,
            )
            self.write_status(
                root,
                [self.status_row("graph", "graph/a.sql", "PASS", str(run_dir))],
            )
            (root / "comparison.csv").write_text("old\n", encoding="utf-8")

            result = self.run_summarizer(root)
            self.assertEqual(result.returncode, 2)
            self.assertIn("threads differs across configurations", result.stderr)
            self.assertEqual(
                (root / "comparison.csv").read_text(encoding="utf-8"), "old\n"
            )

    def test_t1_summary_requires_exactly_one_measured_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self.create_run(
                root,
                "graph",
                "graph/a.sql",
                t1_medians=("12", "6", "3"),
            )
            t1_path = run_dir / "timing" / "t1_summary.tsv"
            rows = read_tsv(t1_path)
            for row in rows:
                row["measured_runs"] = "3"
            write_tsv(
                t1_path,
                ("configuration", "median_seconds", "measured_runs", "threads"),
                rows,
            )
            self.write_status(
                root,
                [self.status_row("graph", "graph/a.sql", "PASS", str(run_dir))],
            )

            result = self.run_summarizer(root)
            self.assertEqual(result.returncode, 2)
            self.assertIn(
                "every T1 configuration must use one measured run", result.stderr
            )

    def test_print_row_outputs_one_block_without_writing_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self.create_run(root, "graph", "graph/a.sql")
            self.write_status(
                root,
                [
                    self.status_row("graph", "graph/a.sql", "PASS", str(run_dir)),
                    self.status_row(
                        "job", "job/not ready.sql", "FAIL", phase="timing timeout",
                        detail='timeout after 1800s: "native"',
                    ),
                ],
            )

            result = self.run_summarizer(root, print_row=2, total=206)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count("=" * 100), 1)
            self.assertIn(
                "[  2/206] not ready                            correct=NA "
                "reorder=- selected=-",
                result.stdout,
            )
            self.assertIn('comparison=[status=FAIL phase="timing timeout"', result.stdout)
            self.assertIn('detail="timeout after 1800s: \\"native\\""', result.stdout)
            for output_name in (
                "comparison.tsv", "comparison.csv", "comparison.log",
                "summary.tsv", "failures.tsv",
            ):
                self.assertFalse((root / output_name).exists(), output_name)

    def test_nonpass_correctness_is_independent_of_terminal_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            timed_out = root / "runs" / "graph" / "timed_out"
            write_tsv(
                timed_out / "correctness" / "row_counts.tsv",
                ("configuration", "rows"),
                [
                    {"configuration": name, "rows": "9"}
                    for name in ("native", "pgplan", "outer_yan")
                ],
            )
            (timed_out / "correctness" / "status.txt").write_text(
                "PASS: exact multisets match\n", encoding="utf-8"
            )
            timed_out_provenance = timed_out / "provenance" / "manifest.txt"
            timed_out_provenance.parent.mkdir(parents=True)
            timed_out_provenance.write_text(
                "execution_db=/data/target.duckdb\n"
                "correctness_db=/data/bounded.duckdb\n",
                encoding="utf-8",
            )
            write_tsv(
                timed_out / "correctness" / "multiset_sha256.tsv",
                ("sha256", "rows"),
                [{"sha256": "b" * 64, "rows": "9"}],
            )
            mismatch = root / "runs" / "job" / "mismatch"
            mismatch_correctness = mismatch / "correctness"
            mismatch_correctness.mkdir(parents=True)
            (mismatch_correctness / "pgplan.comparison.txt").write_text(
                "FAIL native != pgplan\n", encoding="utf-8"
            )
            logs = root / "logs"
            logs.mkdir()
            timeout_log = logs / "graph__timed_out__experiment.log"
            timeout_log.write_text("timing timeout\n", encoding="utf-8")
            self.write_status(
                root,
                [
                    self.status_row(
                        "graph", "graph/timed_out.sql", "SKIP",
                        result_dir=str(timed_out), phase="execute_timeout",
                    ),
                    self.status_row(
                        "job", "job/mismatch.sql", "FAIL",
                        result_dir=str(mismatch), phase="execute",
                    ),
                ],
            )

            result = self.run_summarizer(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = read_tsv(root / "comparison.tsv")
            self.assertEqual(rows[0]["pgplan_comparison_status"], "SKIP")
            self.assertEqual(rows[0]["correct"], "TRUE")
            self.assertEqual(rows[0]["rows"], "9")
            self.assertEqual(rows[0]["pgplan_correctness_scope"], "bounded")
            self.assertEqual(rows[0]["pgplan_correctness_sha256"], "b" * 64)
            self.assertEqual(
                rows[0]["pgplan_comparison_diagnostic_log"], str(timeout_log.resolve())
            )
            self.assertEqual(rows[1]["pgplan_comparison_status"], "FAIL")
            self.assertEqual(rows[1]["correct"], "FALSE")
            log_text = (root / "comparison.log").read_text(encoding="utf-8")
            self.assertIn("timed_out                            correct=TRUE", log_text)
            self.assertIn("comparison=[status=SKIP", log_text)
            self.assertIn("mismatch                             correct=FALSE", log_text)
            self.assertIn("comparison=[status=FAIL", log_text)


if __name__ == "__main__":
    unittest.main()
