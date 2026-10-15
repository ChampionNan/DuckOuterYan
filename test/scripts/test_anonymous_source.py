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
