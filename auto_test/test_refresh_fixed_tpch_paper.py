"""Numeric-only manuscript edits, independent of private measurement files."""
import unittest

import refresh_fixed_tpch_paper as update


class NumericUpdateTests(unittest.TestCase):
    def paper(self):
        runtime = [{"family": family, "counts": {"valid": n},
                    "speedup": {"geomean": 1.84859049, "median": 1.36, "max": 135.595}}
                   for family, n in zip(update.FAMILIES, (47, 80, 45, 109, 281))]
        phase = [{"family": "all" if family == "All" else family, "profiles": row["counts"]["valid"],
                  "cpu_weighted_fraction": dict(round1=.16, round2=.11, round3=.43, other=.30)}
                 for family, row in zip(update.FAMILIES, runtime)]
        reps = [dict(short_query=name, duckdb_s=2., outeryan_s=1., duckdb_optimizer_ms=.5,
                     outeryan_optimizer_ms=2., duckdb_optimizer_percent=.025,
                     outeryan_optimizer_percent=13.99 if name == "A-G-LD-05" else .2)
                for name in ["A-G-LD-05", "Q-H-LD-04", "A-D-LD-05"] + [f"Q-{i}" for i in range(9)]]
        return {"runtime": {"outeryan_selected": runtime}, "phase": phase, "representatives": reps}

    def test_only_fix_contents_change_and_pg_is_untouched(self):
        original = update.TEMPLATE.read_text()
        result = update.numeric_update(original, self.paper())
        self.assertEqual(update.FIX.sub("FIX", original), update.FIX.sub("FIX", result))
        self.assertIn(r"\fix{$1.85\times$}", result)
        self.assertIn(r"\fix{11 of the 12 queries}", result)
        start = r"\paragraph{PostgreSQL Plan Comparison. }"
        end = r"\paragraph{Execution Breakdown}"
        self.assertEqual(original.split(start, 1)[1].split(end, 1)[0],
                         result.split(start, 1)[1].split(end, 1)[0])

    def test_stale_causal_text_is_not_silently_retargeted(self):
        paper = self.paper()
        paper["representatives"][1]["outeryan_optimizer_percent"] = 20
        with self.assertRaisesRegex(ValueError, "unchanged optimization prose"):
            update.numeric_update(update.TEMPLATE.read_text(), paper)

    def test_template_change_requires_a_matching_mapping(self):
        with self.assertRaisesRegex(ValueError, "Expected"):
            update.replace_values(r"\fix{3} and \fix{5}", [4])


if __name__ == "__main__":
    unittest.main()
