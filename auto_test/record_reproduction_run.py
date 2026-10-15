#!/usr/bin/env python3
"""Record source, binary, dataset provenance and software for a fresh run."""
import argparse
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from fetch_benchmark_data import digest


def output(command):
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.strip() if result.returncode == 0 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    binary = Path(os.environ["DUCKDB_BIN"]).resolve()
    manifest = root / "auto_test/outerjoin_benchmark/benchmark/manifest.csv"
    env_names = ("TPCH_SF", "TPCDS_SF", "OY_THREADS", "OY_THREAD_COUNTS", "OY_RUNS",
                 "OY_PROFILE", "OY_CHECK_CORRECTNESS", "OY_TIMEOUT_SECS",
                 "OY_DUCKDB_TIMEOUT_SECS", "OY_OUTERYAN_TIMEOUT_SECS")
    databases = {}
    for key in ("GRAPH_DB", "GRAPH_EPINIONS_DB", "TPCH_DB", "TPCDS_DB", "JOB_DB"):
        path = Path(os.environ[key]).resolve()
        sidecar = path.with_name(path.name + ".reproduction.json")
        databases[key] = dict(path=str(path), provenance=json.loads(sidecar.read_text()) if sidecar.exists() else None)
    report = dict(commit=output(["git", "-C", str(root), "rev-parse", "HEAD"]),
                  tracked_changes=output(["git", "-C", str(root), "diff", "HEAD", "--name-only"]),
                  host=platform.node(), platform=platform.platform(), machine=platform.machine(),
                  cpu_count=os.cpu_count(), python=sys.version, python_executable=sys.executable,
                  packages=sorted(f"{d.metadata['Name']}=={d.version}" for d in distributions()),
                  binary=str(binary), binary_sha256=digest(binary),
                  manifest_sha256=digest(manifest), databases=databases,
                  settings={key: os.environ.get(key) for key in env_names}, cli_arguments=args.arguments,
                  note="CLI overrides defaults; per-query CSV fields are authoritative. "
                       "SQL is byte-reproducible; plan selection and timings are measured anew.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Reproduction environment: {args.output}")


if __name__ == "__main__":
    main()
