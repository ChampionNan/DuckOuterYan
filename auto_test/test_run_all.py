#!/usr/bin/env python3
"""Exercise run_all query selection without building databases or DuckDB."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent


class RunAllSelectionTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="outeryan-run-all-")
        self.root = Path(self.scratch.name)
        self.scripts = self.root / "auto_test"
        self.scripts.mkdir()
        for name in ("configs.sh", "thread_sweep.sh", "run_all.sh"):
            shutil.copyfile(SCRIPT_DIR / name, self.scripts / name)

        self.log = self.root / "calls.jsonl"
        self.duckdb = self.root / "duckdb"
        self.duckdb.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        self.duckdb.chmod(0o755)

        (self.scripts / "build_db.sh").write_text(
            "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
        )
        (self.scripts / "build_db.sh").chmod(0o755)
        (self.scripts / "gen_outerjoin_benchmark.py").write_text(
            textwrap.dedent(
                """
                import json
                import os
                import sys
                with open(os.environ["RUN_ALL_TEST_LOG"], "a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"kind": "generate", "args": sys.argv[1:]}) + "\\n")
                """
            ).lstrip(),
            encoding="utf-8",
        )
        (self.scripts / "record_experiment.py").write_text(
            textwrap.dedent(
                """
                import json
                import os
                import pathlib
                import sys

                args = sys.argv[1:]
                with open(os.environ["RUN_ALL_TEST_LOG"], "a", encoding="utf-8") as handle:
                    handle.write(json.dumps({
                        "kind": "experiment",
                        "args": args,
                        "corpus_present": "OY_CORPUS" in os.environ,
                    }) + "\\n")
                for option in ("-o", "--out"):
                    if option in args:
                        output = pathlib.Path(args[args.index(option) + 1])
                        output.parent.mkdir(parents=True, exist_ok=True)
                        output.write_text("ok\\n", encoding="utf-8")
                        output.with_suffix(".csv").write_text("query\\n", encoding="utf-8")
                        break
                """
            ).lstrip(),
            encoding="utf-8",
        )
        (self.scripts / "experiment_onoff.sh").write_text(
            "#!/usr/bin/env bash\n"
            'exec "$PYTHON_BIN" "$(dirname "$0")/record_experiment.py" "$@"\n',
            encoding="utf-8",
        )
        (self.scripts / "experiment_onoff.sh").chmod(0o755)

    def tearDown(self):
        self.scratch.cleanup()

    def run_driver(self, *args, **overrides):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("OY_", "PGPLAN_", "PG_REPLAY_", "DUCKDB_"))
        }
        env.update(
            {
                "DUCKDB_BIN": str(self.duckdb),
                "PYTHON_BIN": sys.executable,
                "RUN_ALL_TEST_LOG": str(self.log),
                "RUN_PGPLAN": "0",
                "SKIP_BUILD": "1",
                "SKIP_DATA": "1",
                "OY_THREADS": "2",
                "OY_THREAD_COUNTS": "2",
            }
        )
        env.update(overrides)
        return subprocess.run(
            ["bash", str(self.scripts / "run_all.sh"), *args],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_default_regenerates_and_runs_all_versions(self):
        result = self.run_driver()
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = [call["args"] for call in self.calls() if call["kind"] == "generate"]
        self.assertEqual(
            generated,
            [["--version", "v1"], ["--version", "v2"], ["--version", "v3"]],
        )
        experiment = next(call for call in self.calls() if call["kind"] == "experiment")
        self.assertIn("--all", experiment["args"])
        self.assertFalse(experiment["corpus_present"])

    def test_v2_regenerates_dependencies_and_runs_only_v2(self):
        result = self.run_driver("--version", "v2")
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = [call["args"] for call in self.calls() if call["kind"] == "generate"]
        self.assertEqual(generated, [["--version", "v1"], ["--version", "v2"]])
        experiment = next(call for call in self.calls() if call["kind"] == "experiment")
        version_index = experiment["args"].index("--version")
        self.assertEqual(experiment["args"][version_index + 1], "v2")
        self.assertNotIn("--all", experiment["args"])
        self.assertFalse(experiment["corpus_present"])

    def test_version_and_all_are_mutually_exclusive(self):
        result = self.run_driver("--version", "v1", "--all")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--all cannot be combined with --version", result.stderr)


if __name__ == "__main__":
    unittest.main()
