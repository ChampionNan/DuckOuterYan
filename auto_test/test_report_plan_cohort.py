"""Timeout proxy values must never overwrite raw observations or invent fallbacks' times."""
import copy
import math
import unittest

import report_plan_cohort as report


class ReportPlanCohortTest(unittest.TestCase):
    def member(self, role="selected"):
        return dict(query_id="query", family="graph", role=role, content_sha256="hash",
                    decision_source="source.csv", decision_query="query")

    def raw(self, **changes):
        row = dict(sql_content_sha256="hash", selected_plan="OUTERYAN", correct="NOT-CHECKED",
                   timing_status="measured", duckdb_status="measured", outeryan_status="measured",
                   tm_off="4", tm_on="2", duckdb_timeout_seconds="600")
        row.update(changes)
        return row

    def test_timeout_proxy_preserves_observation(self):
        raw = self.raw(tm_off="", tm_on=".04", duckdb_status="timeout", timing_status="timeout",
                       duckdb_timeout_stage="warmup")
        original = copy.deepcopy(raw)
        row = report.observation(self.member(), raw)
        self.assertEqual(raw, original)
        self.assertEqual(row["speedup"], 15000)
        self.assertEqual(row["recorded_duckdb_s"], "")
        self.assertEqual(row["duckdb_status"], "timeout")
        self.assertEqual(row["speedup_source"], "duckdb_timeout_600s")

    def test_other_timeouts_and_bad_limits_are_excluded(self):
        for changes in (dict(outeryan_status="timeout"),
                        dict(duckdb_status="timeout", outeryan_status="timeout"),
                        dict(duckdb_status="timeout", duckdb_timeout_seconds="900"),
                        dict(duckdb_status="timeout", tm_on="nan"), dict(correct="FALSE")):
            self.assertIsNone(report.observation(self.member(), self.raw(**changes))["speedup"])

    def test_default_one_is_not_a_runtime(self):
        row = report.observation(self.member("cost_control"), self.raw(
            selected_plan="DUCKDB", timing_status="fallback-skip", duckdb_status="fallback-skip",
            outeryan_status="fallback-skip", tm_off="", tm_on=""))
        self.assertEqual(row["speedup"], 1)
        self.assertIsNone(row["effective_duckdb_s"])
        measured = report.observation(self.member(), self.raw())
        result = report.summarize([row, measured], "All", "all_queries")
        self.assertAlmostEqual(result["geomean"], 2 ** .5)
        self.assertEqual(result["effective_pair_n"], 1)
        self.assertEqual(result["effective_total_ratio"], 2)

    def test_complete_current_cohort(self):
        if not all((report.ROOT / item["path"]).is_file()
                   for item in report.cohort.policy()["source_files"] + report.cohort.query_updates.source_files()):
            self.skipTest("Historical measurement CSVs are optional local artifacts")
        details, retired, stats, summary = report.build()
        self.assertEqual(len(details), 321)
        self.assertEqual(len(retired), 21)
        all_queries = next(r for r in stats if r["scope"] == "all_queries" and r["family"] == "All")
        self.assertEqual((all_queries["measured_n"], all_queries["capped_n"], all_queries["fallback_n"]),
                         (278, 4, 39))
        self.assertEqual(all_queries["excluded_n"], 0)
        self.assertAlmostEqual(all_queries["geomean"], math.prod(r["speedup"] ** (1 / 321) for r in details))
        self.assertEqual(all_queries["max"], max(r["speedup"] for r in details))
        self.assertEqual(all_queries["measured_max"],
                         max(r["speedup"] for r in details if r["speedup_source"] == "measured"))
        self.assertEqual(summary["benchmark_queries"], 321)

    def test_promoted_candidates_use_exact_latest_observations(self):
        sources = report.cohort.policy()["source_files"] + report.cohort.query_updates.source_files()
        if not all((report.ROOT / r["path"]).exists() for r in sources):
            self.skipTest("Pinned historical measurements are optional local artifacts")
        details, _, _, _ = report.build()
        by_id = {row["query"]: row for row in details}
        self.assertTrue(report.cohort.RETIRED_FAMILY_MINIMA.isdisjoint(by_id))
        for entry in report.cohort.query_updates.policy()["replacements"]:
            if entry["original_query"] in report.cohort.RETIRED_FAMILY_MINIMA:
                continue
            row = by_id[entry["query_id"]]
            self.assertEqual(row["source_query"], entry["measurement_query"])
            self.assertEqual(row["source_csv"], entry["measurement_csv"])
            self.assertEqual(row["source_sql_content_sha256"], entry["measurement_content_sha256"])
            self.assertEqual(row["speedup_source"], "measured")
            self.assertEqual(row["selected_plan"], "OUTERYAN")
            self.assertGreaterEqual(row["speedup"], .7)
        # The explicitly retired JOB slot must not become a synthetic 1x result.
        self.assertNotIn(report.cohort.RETIRED_JOB_QUERY, by_id)
        remaining = [r for r in details if r["speedup"] is not None and r["speedup"] < .7]
        self.assertEqual(remaining, [])


if __name__ == "__main__":
    unittest.main()
