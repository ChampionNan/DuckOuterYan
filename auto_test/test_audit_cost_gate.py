#!/usr/bin/env python3

import importlib.util
import unittest
from pathlib import Path


AUDIT_PATH = Path(__file__).with_name("audit_cost_gate.py")
SPEC = importlib.util.spec_from_file_location("audit_cost_gate", AUDIT_PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def normal_row(query, *, reordered="1", selected="0", plan="DUCKDB", reason="COST_DUCKDB_BETTER"):
    gate_result = "PASS" if reason in AUDIT.SELECT_REASONS else "FAIL"
    cost_gate_applied = "1"
    if reason == "COST_UNAVAILABLE":
        gate_result = "UNAVAILABLE"
        cost_gate_applied = "0"
    return {
        "query": query,
        "family": "tpch",
        "sql_path": f"tpch/{query}.sql",
        "outer_reordered": reordered,
        "outer_yan_selected": selected,
        "selected_plan": plan,
        "decision_reason": reason,
        "selection_mode": "GATED",
        "cost_gate_applied": cost_gate_applied,
        "gate_result": gate_result,
        "correct": "TRUE",
        "note": "OK",
        "rows": "12",
        "effective_pass": "main",
        "formula_id": "V4",
        "relation_count": "5",
        "baseline_proven_empty": "0",
        "baseline_cost": "100",
        "candidate_join_cost": "70",
        "semijoin_raw_cost": "50",
        "semijoin_cost_ratio": "0.35",
        "candidate_total": "87.5",
        "raw_cost_ratio": "0.875",
        "candidate_to_baseline_join_input_ratio": "0.7",
        "inner_output_weight": "1",
        "unmatched_left_weight": "1",
        "unmatched_right_weight": "1",
        "semijoin_materialize_weight": "1",
        "semijoin_filter_build_weight": "1",
        "semijoin_replay_weight": "1",
        "semijoin_probe_lookup_weight": "1",
        "semijoin_probe_emit_weight": "1",
    }


def forced_row(query, *, tm="1.20", t1="1.10", correct="TRUE"):
    row = normal_row(
        query,
        selected="1",
        plan="OUTERYAN",
        reason="FORCE_OUTERYAN_DIAGNOSTIC",
    )
    row.update({
        "correct": correct,
        "note": "OK" if correct == "TRUE" else "NOT-EQUIV",
        "selection_mode": "FORCE_OUTERYAN_DIAGNOSTIC",
        "cost_gate_applied": "0",
        "gate_result": "SKIPPED",
        "tm_speedup": tm,
        "t1_speedup": t1,
        "tm_off": tm,
        "tm_on": "1",
        "t1_off": t1,
        "t1_on": "1",
    })
    return row


class SpeedupClassificationTest(unittest.TestCase):
    def test_symmetric_materiality_band(self):
        self.assertEqual(AUDIT.speedup_outcome("1.10", 1.10), "faster")
        self.assertEqual(AUDIT.speedup_outcome("0.909090909", 1.10), "slower")
        self.assertEqual(AUDIT.speedup_outcome("1.05", 1.10), "neutral")
        self.assertEqual(AUDIT.speedup_outcome("NA", 1.10), "unmeasured")

    def test_gate_confusion_classes(self):
        self.assertEqual(AUDIT.gate_judgment(True, "faster"), "true_positive")
        self.assertEqual(AUDIT.gate_judgment(False, "faster"), "false_negative")
        self.assertEqual(AUDIT.gate_judgment(True, "slower"), "false_positive")
        self.assertEqual(AUDIT.gate_judgment(False, "slower"), "true_negative")

    def test_thread_sensitive_consensus(self):
        self.assertEqual(AUDIT.outcome_consensus("faster", "slower"), "thread_sensitive")
        self.assertEqual(AUDIT.outcome_consensus("faster", "faster"), "faster_both")


class CostGateAuditTest(unittest.TestCase):
    def audit(self, normal, forced):
        return AUDIT.audit_rows(normal, forced, Path("forced.csv"), 1.10, "tm")

    def test_only_changed_groupings_are_audited(self):
        normal = [normal_row("changed"), normal_row("same", reordered="0")]
        rows = self.audit(normal, [forced_row("changed"), forced_row("same")])
        self.assertEqual([row["query"] for row in rows], ["changed"])

    def test_proven_empty_baseline_is_not_audited(self):
        empty = normal_row("empty")
        empty["baseline_proven_empty"] = "1"
        self.assertEqual(len(AUDIT.changed_grouping_rows([empty])), 1)
        self.assertEqual(self.audit([empty], [forced_row("empty")]), [])

    def test_selected_winner_and_rejected_loser(self):
        selected = normal_row(
            "selected",
            selected="1",
            plan="OUTERYAN",
            reason="COST_OUTERYAN_BETTER",
        )
        rejected = normal_row("rejected")
        rows = self.audit(
            [selected, rejected],
            [forced_row("selected", tm="1.30"), forced_row("rejected", tm="0.70")],
        )
        by_query = {row["query"]: row for row in rows}
        self.assertEqual(by_query["selected"]["tm_gate_judgment"], "true_positive")
        self.assertEqual(by_query["rejected"]["tm_gate_judgment"], "true_negative")

    def test_false_positive_and_false_negative(self):
        selected = normal_row(
            "selected",
            selected="1",
            plan="OUTERYAN",
            reason="COST_OUTERYAN_BETTER",
        )
        rejected = normal_row("rejected")
        rows = self.audit(
            [selected, rejected],
            [forced_row("selected", tm="0.50"), forced_row("rejected", tm="2.00")],
        )
        by_query = {row["query"]: row for row in rows}
        self.assertEqual(by_query["selected"]["tm_gate_judgment"], "false_positive")
        self.assertEqual(by_query["rejected"]["tm_gate_judgment"], "false_negative")

    def test_incorrect_candidate_is_never_a_performance_win(self):
        selected = normal_row(
            "bad",
            selected="1",
            plan="OUTERYAN",
            reason="COST_OUTERYAN_BETTER",
        )
        row = self.audit([selected], [forced_row("bad", tm="10", correct="FALSE")])[0]
        self.assertEqual(row["tm_outcome"], "incorrect")
        self.assertEqual(row["tm_gate_judgment"], "unsafe_selection")

    def test_missing_forced_result_is_explicit(self):
        row = self.audit([normal_row("missing")], [])[0]
        self.assertEqual(row["primary_gate_judgment"], "missing_forced_result")

    def test_formula_mismatch_is_not_compared(self):
        forced = forced_row("mismatch")
        forced["formula_id"] = "V5"
        row = self.audit([normal_row("mismatch")], [forced])[0]
        self.assertEqual(row["tm_gate_judgment"], "input_mismatch")

    def test_cost_mismatch_is_not_compared(self):
        forced = forced_row("mismatch")
        forced["candidate_total"] = "88"
        row = self.audit([normal_row("mismatch")], [forced])[0]
        self.assertEqual(row["costs_match"], "FALSE")
        self.assertEqual(row["tm_gate_judgment"], "input_mismatch")

    def test_cost_unavailable_can_match_identical_sentinels(self):
        normal = normal_row("unavailable", reason="COST_UNAVAILABLE")
        forced = forced_row("unavailable", tm="0.8")
        for column in AUDIT.COST_COLUMNS:
            normal[column] = "NA"
            forced[column] = "NA"
        row = self.audit([normal], [forced])[0]
        self.assertEqual(row["costs_match"], "TRUE")
        self.assertEqual(row["tm_gate_judgment"], "true_negative")

    def test_forced_reorder_mismatch_is_not_compared(self):
        forced = forced_row("same")
        forced["outer_reordered"] = "0"
        row = self.audit([normal_row("same")], [forced])[0]
        self.assertEqual(row["forced_reorder_match"], "FALSE")
        self.assertEqual(row["tm_gate_judgment"], "candidate_unavailable")

    def test_non_diagnostic_forced_row_is_not_compared(self):
        forced = forced_row("not_diagnostic")
        forced["decision_reason"] = "FORCE_OUTERYAN"
        row = self.audit([normal_row("not_diagnostic")], [forced])[0]
        self.assertEqual(row["tm_gate_judgment"], "candidate_unavailable")

    def test_non_gated_normal_row_is_not_compared(self):
        normal = normal_row("forced")
        normal["selection_mode"] = "FORCE_OUTERYAN"
        row = self.audit([normal], [forced_row("forced")])[0]
        self.assertEqual(row["normal_gate_valid"], "FALSE")
        self.assertEqual(row["tm_gate_judgment"], "invalid_normal_gate_state")

    def test_precise_times_override_rounded_reported_speedup(self):
        forced = forced_row("boundary", tm="1.100")
        forced["tm_off"] = "1.0996"
        row = self.audit([normal_row("boundary")], [forced])[0]
        self.assertEqual(row["forced_reported_tm_speedup"], "1.100")
        self.assertEqual(row["tm_outcome"], "neutral")


if __name__ == "__main__":
    unittest.main()
