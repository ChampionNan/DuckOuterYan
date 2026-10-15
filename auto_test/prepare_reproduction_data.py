#!/usr/bin/env python3
"""Prepare all five routed databases in staging, then publish validated files.

Existing files are never overwritten. Databases prepared by this entry point have
a sidecar recording their scale, source hashes, generator binary and catalog.
Legacy databases without that provenance require explicit --skip-data reuse.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile

from fetch_benchmark_data import CHECKSUMS, digest

SCRIPT = Path(__file__).resolve().parent


def specifications(env):
    root = SCRIPT.parent
    return [
        dict(kind="graph", dataset="bitcoin", path=env.get("GRAPH_DB", str(root / "graph_db"))),
        dict(kind="graph", dataset="epinions", path=env.get("GRAPH_EPINIONS_DB", str(root / "graph_epinions.duckdb"))),
        *[dict(kind=kind, scale=str(env.get(kind.upper() + "_SF", "50")),
               path=env.get(kind.upper() + "_DB", str(root / (kind + "_" + env.get(kind.upper() + "_SF", "50") + ".duckdb"))))
          for kind in ("tpch", "tpcds")],
        dict(kind="job", path=env.get("JOB_DB", str(root / "job_db"))),
    ]


def query(binary, db, sql):
    result = subprocess.run([str(binary), str(db), "-readonly", "-json", "-c", sql],
                            check=True, text=True, stdout=subprocess.PIPE)
    return json.loads(result.stdout)


def catalog(binary, db, kind):
    tables = query(binary, db, "SELECT table_name FROM duckdb_tables() WHERE NOT internal ORDER BY table_name")
    expected_tables, expected_keys = {"graph": (10, 0), "tpch": (8, 7), "tpcds": (24, 17), "job": (21, 21)}[kind]
    if len(tables) != expected_tables:
        raise ValueError(f"Incomplete {kind} database: {db}; expected {expected_tables} tables")
    keys = query(binary, db, "SELECT table_name, constraint_text FROM duckdb_constraints() "
                 "WHERE constraint_type='PRIMARY KEY' ORDER BY table_name, constraint_text")
    if len(keys) != expected_keys:
        raise ValueError(f"Incomplete {kind} primary keys: {db}; expected {expected_keys}")
    counts = {}
    for row in tables:
        name = row["table_name"]
        counts[name] = query(binary, db, 'SELECT count(*) AS n FROM "' + name.replace('"', '""') + '"')[0]["n"]
    if any(count <= 0 for count in counts.values()):
        raise ValueError(f"Empty table in {db}")
    return dict(rows=counts, primary_keys=keys)


def prepare(spec, binary):
    target = Path(spec["path"]).resolve()
    sidecar = target.with_name(target.name + ".reproduction.json")
    identity = {key: value for key, value in spec.items() if key != "path"}
    if target.exists():
        if not sidecar.is_file():
            raise ValueError(f"Existing database has no reproduction sidecar: {target}. "
                             "Preserve it; choose new *_DB paths for a verified rebuild, or use "
                             "--skip-data only if you have independently verified the existing data.")
        recorded = json.loads(sidecar.read_text())
        if recorded["identity"] != identity or recorded["data_checksums_sha256"] != digest(CHECKSUMS):
            raise ValueError(f"Existing database scale/source mismatch: {target}")
        if catalog(binary, target, spec["kind"]) != recorded["catalog"]:
            raise ValueError(f"Database catalog/row counts changed: {target}")
        print(f"[reuse verified] {target}", flush=True)
        return
    if sidecar.exists() or Path(str(target) + ".wal").exists():
        raise ValueError(f"Orphaned metadata/WAL beside {target}; inspect it before retrying")
    target.parent.mkdir(parents=True, exist_ok=True)
    # The temporary directory is on the destination filesystem. Interruptions
    # cannot leave a partial file at the configured database path.
    with tempfile.TemporaryDirectory(prefix=".outeryan-build-", dir=target.parent) as temp:
        stage = Path(temp) / "data.duckdb"
        env = dict(os.environ, FORCE="0", OY_STRICT_DATA_BUILD="1", DUCKDB_BIN=str(binary))
        env[spec["kind"].upper() + "_DB"] = str(stage)
        if spec["kind"] == "graph":
            env["GRAPH_DATASET"] = spec["dataset"]
        elif spec["kind"] in ("tpch", "tpcds"):
            env[spec["kind"].upper() + "_SF"] = spec["scale"]
        subprocess.run(["bash", str(SCRIPT / "build_db.sh"), spec["kind"]], env=env, check=True)
        info = dict(identity=identity, data_checksums_sha256=digest(CHECKSUMS),
                    binary_sha256=digest(binary), catalog=catalog(binary, stage, spec["kind"]))
        if Path(str(stage) + ".wal").exists():
            raise ValueError(f"Uncheckpointed database: {stage}")
        metadata = Path(temp) / "metadata.json"
        metadata.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
        os.link(stage, target)  # O_EXCL semantics; never overwrite existing data.
        os.link(metadata, sidecar)
    print(f"[prepared and verified] {target}", flush=True)


def main():
    binary = Path(os.environ["DUCKDB_BIN"]).resolve()
    if os.environ.get("GRAPH_DATASET", "bitcoin") != "bitcoin":
        raise ValueError("The frozen workload routes Bitcoin and Epinions separately; GRAPH_DATASET must be bitcoin")
    specs = specifications(os.environ)
    if len({Path(spec["path"]).resolve() for spec in specs}) != len(specs):
        raise ValueError("Database paths must be distinct for each dataset/scale")
    for spec in specs:
        prepare(spec, binary)


if __name__ == "__main__":
    main()
