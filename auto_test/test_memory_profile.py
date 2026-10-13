import copy
import json
from pathlib import Path
import tempfile
import unittest

import memory_profile as m


def node(name, memory, children=None):
    return dict(operator_name=name, operator_type=name, system_peak_buffer_memory=memory,
                system_peak_temp_dir_size=0, operator_timing=0.01, children=children or [])


def sample_profile():
    return dict(query_name="SELECT 42;", system_peak_buffer_memory=300,
                system_peak_temp_dir_size=0, latency=0.04,
                children=[node("PROJECTION", 90, [
                    node("HASH_JOIN", 300, [node("SJ_PROBE_ROUND_1", 200),
                                             node("SJ_BUILD_ROUND_1", 100),
                                             node("SJ_BUILD_ROUND_2", 250)])])])


class MemoryTests(unittest.TestCase):
    def test_phase_peaks_are_max_not_sum(self):
        result = m.profile_metrics(sample_profile(), "SELECT 42;")
        self.assertEqual(result["phases"]["round1"]["buffer_peak_bytes"], 200)
        self.assertEqual(result["phases"]["round2"]["buffer_peak_bytes"], 250)
        self.assertEqual(result["phases"]["round3"]["buffer_peak_bytes"], 300)
        self.assertEqual(result["phases"]["other"]["buffer_peak_bytes"], 90)
        self.assertEqual(result["buffer_peak_bytes"], 300)

    def test_absent_round_is_null(self):
        root = sample_profile()
        root["children"] = [node("HASH_JOIN", 300)]
        result = m.profile_metrics(root, "SELECT 42;")
        self.assertIsNone(result["phases"]["round1"]["buffer_peak_bytes"])
        self.assertEqual(result["phases"]["round1"]["operator_count"], 0)

    def test_old_build_zero_children_and_stale_root_are_rejected(self):
        root = sample_profile()
        root["children"] = [node("HASH_JOIN", 0)]
        with self.assertRaisesRegex(ValueError, "missing/stale"):
            m.profile_metrics(root, "SELECT 42;")
        root = sample_profile()
        root[m.MEMORY] = 900
        with self.assertRaisesRegex(ValueError, "missing/stale"):
            m.profile_metrics(root, "SELECT 42;")

    def test_missing_and_invalid_metrics(self):
        for bad in (-1, float("nan"), float("inf")):
            root = sample_profile()
            root[m.MEMORY] = bad
            with self.assertRaises(ValueError):
                m.profile_metrics(root, "SELECT 42;")
        root = sample_profile()
        del root["children"][0][m.MEMORY]
        with self.assertRaises(ValueError):
            m.profile_metrics(root, "SELECT 42;")

    def test_query_identity(self):
        with self.assertRaisesRegex(ValueError, "different query"):
            m.profile_metrics(sample_profile(), "SELECT 43;")

    def test_spill_is_separate_from_ram(self):
        root = sample_profile()
        root[m.SPILL] = 1000
        root["children"][0][m.SPILL] = 1000
        result = m.profile_metrics(root, "SELECT 42;")
        self.assertEqual(result["spill_peak_bytes"], 1000)
        self.assertEqual(result["buffer_peak_bytes"], 300)

    def test_exact_two_bare_executions(self):
        for engine, setting in (("duckdb", "outer_yan"), ("outeryan", "")):
            text = m.session_sql("SELECT 42;", engine, Path("/tmp/a'b.json"), 32, 600)
            self.assertEqual(text.count("SELECT 42;"), 2)
            self.assertEqual(text.count("CALL enable_profiling("), 1)
            self.assertIn("SET max_execution_time=600000;", text)
            self.assertIn("SET disabled_optimizers='{}'".format(setting), text)
            self.assertIn("'/tmp/a''b.json'", text)
            self.assertNotIn("COPY", text)
            self.assertNotIn("LIMIT", text)
            self.assertNotIn("CREATE TABLE", text)
            self.assertLess(text.index("warmup"), text.index("measure"))

    def test_summary_excludes_both_sides_timeouts_and_fallbacks(self):
        good = dict(family="graph", duckdb=dict(status="ok", **m.profile_metrics(sample_profile(), "SELECT 42;")),
                    outeryan=dict(status="ok", **m.profile_metrics(sample_profile(), "SELECT 42;")))
        rows = [good]
        for engine in ("duckdb", "outeryan"):
            row = copy.deepcopy(good)
            row[engine]["status"] = "timeout"
            rows.append(row)
        row = copy.deepcopy(good)
        row["outeryan"]["status"] = "not_selected"
        rows.append(row)
        stats = m.summarize(rows)["groups"]["all"]
        self.assertEqual(stats["attempted"], 4)
        self.assertEqual(stats["valid_pairs"], 1)
        self.assertEqual(stats["excluded"], 3)
        self.assertEqual(stats["round1"]["median_observed_buffer_peak_mib"], 200 / 2**20)

    def test_timeout_does_not_run_measurement_or_prevent_next_side(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "fake_duckdb"
            binary.write_text("#!/usr/bin/env python3\nimport sys\n"
                              "print('OY_MEMORY_STAGE=warmup', flush=True)\n"
                              "print('Interrupt Error: query timeout', flush=True)\nsys.exit(1)\n")
            binary.chmod(0o755)
            for engine in ("duckdb", "outeryan"):
                result = m.run_side(binary, root / "unused", "SELECT 42;", engine, root / engine, 32, 600)
                self.assertEqual(result["status"], "timeout")
                self.assertEqual(result["warmups_completed"], 0)
                self.assertEqual(result["measured_executions_completed"], 0)
                self.assertEqual(result["stage"], "warmup")

    def test_cohort_is_pinned(self):
        cohort = json.loads(m.DEFAULT_COHORT.read_text())
        m.validate(cohort)
        cohort["queries"][0]["sql_sha256"] = "invalid"
        with self.assertRaisesRegex(ValueError, "SQL changed"):
            m.validate(cohort)


if __name__ == "__main__":
    unittest.main()
