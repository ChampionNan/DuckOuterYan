"""Validate the frozen Graph definitions without running calibration or queries."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import graph_dataset_policy as policy


class GraphDatasetPolicyTests(unittest.TestCase):
    def check_spec(self, spec):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps(spec))
            return policy.load_policy(path)

    def test_both_frozen_batches_load(self):
        for path, count in ((policy.POLICY, 16),
                            (policy.POLICY.with_name("graph_dataset_extension_20261010.json"), 3)):
            with self.subTest(path=path.name):
                spec = policy.load_policy(path)
                self.assertEqual(len(spec["replacements"]), count)
                self.assertEqual(spec["target_dataset"], "epinions")

    def test_invalid_definitions_fail_closed(self):
        original = policy.load_policy()
        mutations = (
            lambda s: s.update(expected_queries=99),
            lambda s: s.update(target_dataset="wiki"),
            lambda s: s["replacements"].append(copy.deepcopy(s["replacements"][0])),
            lambda s: s["replacements"][0].update(semantic_tier="high"),
            lambda s: s["replacements"][0].update(path="../query.sql"),
            lambda s: s["replacements"][0].update(content_sha256="invalid"),
            lambda s: s.update(representation="measurements"),
        )
        for mutate in mutations:
            spec = copy.deepcopy(original)
            mutate(spec)
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                self.check_spec(spec)


if __name__ == "__main__":
    unittest.main()
