"""Cold-start data preparation must fail closed and preserve existing files."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fetch_benchmark_data as fetch
import prepare_reproduction_data as data


class ReproductionDataTest(unittest.TestCase):
    def test_cache_hash_is_checked_not_just_existence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bitcoin.txt"
            path.write_bytes(b"interrupted download")
            with self.assertRaisesRegex(ValueError, "Cached data checksum mismatch"), patch.object(fetch.subprocess, "run") as run:
                fetch.fetch(path)
            run.assert_not_called()
            self.assertEqual(path.read_bytes(), b"interrupted download")

    def test_http_failure_cannot_install_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bitcoin.txt"
            with patch.object(fetch.subprocess, "run", side_effect=RuntimeError("HTTP failure")):
                with self.assertRaisesRegex(RuntimeError, "HTTP failure"):
                    fetch.fetch(path)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_successful_download_is_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "job_test.parquet"
            pins = Path(temp) / "pins.json"
            pins.write_text(json.dumps({path.name: hashlib.sha256(b"data").hexdigest()}))
            def download(args, **kwargs):
                Path(args[args.index("--output") + 1]).write_bytes(b"data")
            with patch.object(fetch, "CHECKSUMS", pins), patch.object(fetch.subprocess, "run", side_effect=download):
                fetch.fetch(path)
            self.assertEqual(path.read_bytes(), b"data")

    def test_scale_routing_is_distinct(self):
        specs = data.specifications(dict(TPCH_SF="50", TPCDS_SF="100"))
        self.assertEqual(len(specs), 5)
        self.assertEqual([spec.get("dataset") for spec in specs[:2]], ["bitcoin", "epinions"])
        self.assertTrue(specs[2]["path"].endswith("tpch_50.duckdb"))
        self.assertTrue(specs[3]["path"].endswith("tpcds_100.duckdb"))

    def test_existing_unknown_database_is_not_touched(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "db"
            target.write_bytes(b"user database")
            with self.assertRaisesRegex(ValueError, "no reproduction sidecar"):
                data.prepare(dict(kind="tpch", scale="50", path=str(target)), Path("duckdb"))
            self.assertEqual(target.read_bytes(), b"user database")

    def test_failed_build_does_not_publish_partial_database(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "tpch_50.duckdb"
            def failed_build(args, env, **kwargs):
                Path(env["TPCH_DB"]).write_bytes(b"partial")
                raise RuntimeError("interrupted")
            with patch.object(data.subprocess, "run", side_effect=failed_build):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    data.prepare(dict(kind="tpch", scale="50", path=str(target)), Path("duckdb"))
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_successful_build_and_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / "duckdb"
            binary.write_bytes(b"binary")
            target = Path(temp) / "tpch_50.duckdb"
            spec = dict(kind="tpch", scale="50", path=str(target))
            def build(args, env, **kwargs):
                self.assertEqual(env["OY_STRICT_DATA_BUILD"], "1")
                self.assertEqual(env["TPCH_SF"], "50")
                Path(env["TPCH_DB"]).write_bytes(b"complete")
            with patch.object(data.subprocess, "run", side_effect=build), patch.object(data, "catalog", return_value=dict(rows=1)):
                data.prepare(spec, binary)
            with patch.object(data.subprocess, "run") as run, patch.object(data, "catalog", return_value=dict(rows=1)):
                data.prepare(spec, binary)
                run.assert_not_called()
                with self.assertRaisesRegex(ValueError, "scale/source mismatch"):
                    data.prepare(dict(spec, scale="100"), binary)
            self.assertEqual(target.read_bytes(), b"complete")


if __name__ == "__main__":
    unittest.main()
