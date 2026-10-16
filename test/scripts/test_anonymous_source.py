"""Publication boundaries: no tracked outputs, measurements, or escaping links."""
import importlib.util
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("anonymous_source", REPO / "scripts/anonymous_source.py")
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)


class AnonymousSourceTest(unittest.TestCase):
    def test_ignore_policy_preserves_inputs_and_rejects_tracked_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_bytes((REPO / ".gitignore").read_bytes())
            files = {
                "src/parser/parsed_data/example.cpp": "int value;\n",
                "auto_test/build_db.sh": "#!/bin/sh\n",
                "auto_test/outerjoin_benchmark/benchmark/tpch/query__db123.sql": "SELECT 1;\n",
                "auto_test/outerjoin_benchmark/benchmark/manifest.csv": "query_id,path\nq,q.sql\n",
                "auto_test/results/run.csv": "tm_off,tm_on\n1,2\n",
                "auto_test/paper_examples/recorded_results/run.json": "{}\n",
                "auto_test/outerjoin_benchmark/candidates/example/pilot_provenance.json": "{}\n",
                "auto_test/outerjoin_benchmark/candidates/example/local_validation.json": "{}\n",
            }
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            output = "auto_test/results/run.csv"
            subprocess.run(["git", "-C", str(root), "add", "-f", output], check=True)
            published, tracked_outputs = source.inventory(root)
            self.assertEqual(tracked_outputs, [output])
            self.assertEqual(set(published), {".gitignore", *list(files)[:4]})

    def test_nested_measurements_and_identity_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "auto_test/policy.json"
            path.parent.mkdir()
            path.write_text('{"nested": [{"tm_off": 1}], "machine": "/Users/example/repo"}')
            errors = source.check(root, [str(path.relative_to(root))])
            self.assertTrue(any("tm_off" in e for e in errors))
            self.assertTrue(any("personal absolute path" in e for e in errors))

    def test_llm_files_and_diagnostic_outputs_are_ignored(self):
        ignored = [
            "AGENTS.md", "auto_test/AGENTS.override.md", "src/CLAUDE.md",
            "CLAUDE.local.md", "CODEX.md", "GEMINI.md", "llms.txt", "llms-full.txt",
            ".claude/settings.local.json", "auto_test/.codex/session.jsonl",
            ".agents/skills/example/SKILL.md", ".cursor/rules/example.mdc",
            ".cursorrules", ".windsurf/rules/example.md", ".windsurfrules",
            ".aider.conf.yml", ".aider.chat.history.md", ".aider.input.history",
            ".aider.tags.cache.v3/entry", ".github/copilot-instructions.md",
            ".github/instructions/example.instructions.md", ".github/prompts/example.prompt.md",
            ".github/agents/example.agent.md", ".github/skills/example/SKILL.md",
            "auto_test/candidates/run.profiles/query.json",
            "auto_test/candidates/run.optimizer/profile.json",
            "auto_test/candidates/run.plans/query.txt",
            "auto_test/candidates/run_statistics/summary.csv",
            "auto_test/candidates/debug_output/dump.txt",
            "auto_test/candidates/debug_dumps/plan.json",
            "profiles/query.json", "traces/query.txt", "plots/figure.svg",
            "reports/summary.csv", "debug_output/query.txt", "debug_dumps/plan.json",
            "query.trace.csv", "query.profile.txt", "query.explain.txt", "query.plan.txt",
            "paper.tex", "auto_test/paper_results_fixed_template.tex",
            "auto_test/outerjoin_benchmark/design.tex",
            "results/run.csv", "auto_test/results/run.csv",
            "auto_test/nested/results/run.json",
            "auto_test/paper_examples/README.md", "auto_test/paper_examples/run_example.py",
            "auto_test/paper_examples/tpch/query.sql",
            "auto_test/pg_oj_trace/witnesses.sql",
            "auto_test/diagnostics/check.sql", "auto_test/outerjoin_query_old/tpch/query.sql",
        ]
        retained = [
            "auto_test/record_reproduction_run.py", "auto_test/phase_profile.sh",
            "src/optimizer/outer_yan/common/outer_yan_trace.cpp",
            "src/main/query_profiler.cpp", "src/common/stacktrace.cpp",
            "tools/shell/tests/test_prompt.py", "data/csv/auto/titlebasicsdebug.tsv",
            "test/sql/aggregate/distinct/grouped/results/fixture.csv",
            "auto_test/outerjoin_benchmark/benchmark/manifest.csv",
            "auto_test/outerjoin_benchmark/sources/policy.json",
            "auto_test/outerjoin_benchmark/benchmark/tpch/query.sql",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_bytes((REPO / ".gitignore").read_bytes())
            result = subprocess.run(
                ["git", "-C", str(root), "check-ignore", "--no-index", "--stdin"],
                input="\n".join(ignored + retained) + "\n", text=True,
                capture_output=True, check=True)
            self.assertEqual(set(result.stdout.splitlines()), set(ignored))

    def test_public_dataset_attribution_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("https://snap.stanford.edu/data/\n")
            self.assertEqual(source.check(root, ["README.md"]), [])

    def test_export_has_neutral_ownership_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            root.mkdir()
            (root / "query.sql").write_text("SELECT 42;\n")
            dest = Path(tmp) / "source.tar.gz"
            source.export(root, ["query.sql"], dest)
            original = dest.read_bytes()
            with tarfile.open(dest) as archive:
                member = archive.getmembers()[0]
                self.assertEqual(member.name, "outeryan/query.sql")
                self.assertEqual((member.uid, member.gid, member.uname, member.gname), (0, 0, "", ""))
                self.assertEqual(archive.extractfile(member).read(), b"SELECT 42;\n")
            with self.assertRaises(FileExistsError):
                source.export(root, ["query.sql"], dest)
            self.assertEqual(dest.read_bytes(), original)

    def test_symlinks_cannot_export_external_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "external").symlink_to("../private-file")
            self.assertTrue(source.check(root, ["external"]))


if __name__ == "__main__":
    unittest.main()
