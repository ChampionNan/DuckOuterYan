#!/usr/bin/env python3
"""Force customer-orders first for the supplied paper query on existing TPC-H SF1."""
import argparse
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MODES = ("off", "on", "controlled_off", "sj_original", "sj_customer_first")


def sha256(path):
    with path.open("rb") as source:
        digest = hashlib.sha256()
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
        return digest.hexdigest()


def inspect_profile(node, expected_pair):
    groups = []
    sj_count = 0

    def visit(item):
        nonlocal sj_count
        tables = set()
        table = item.get("extra_info", {}).get("Table")
        if table:
            tables.add(table.rsplit(".", 1)[-1])
        for child in item.get("children", []):
            tables.update(visit(child))
        name = item.get("operator_name", "").strip()
        if name.startswith("SJ_PROBE"):
            sj_count += 1
        if name.endswith("JOIN"):
            groups.append({"tables": sorted(tables), "kind": item.get("extra_info", {}).get("Join Type"),
                           "rows": item["operator_cardinality"],
                           "input_rows": sum(c["operator_cardinality"] for c in item["children"])})
        return tables

    visit(node)
    expected = {frozenset(expected_pair), frozenset(("customer", "orders", "lineitem"))}
    if len(groups) != 2 or {frozenset(g["tables"]) for g in groups} != expected:
        raise RuntimeError(f"Unexpected physical join grouping: {groups}")
    return {"joins": groups, "sj_probe_count": sj_count,
            "real_join_input_rows": sum(g["input_rows"] for g in groups),
            "nonroot_intermediate_rows": next(g["rows"] for g in groups if len(g["tables"]) == 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "tpch_db")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build/release")
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument("--runs", type=int, default=11)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.threads < 1 or args.runs < 2:
        parser.error("threads must be positive and runs at least 2")
    db = args.db.resolve()
    build = args.build_dir.resolve()
    query = HERE / "tpch/customer_orders_lineitem.sql"
    library = next((build / "src" / name for name in ("libduckdb.dylib", "libduckdb.so")
                    if (build / "src" / name).is_file()), None)
    if not db.is_file() or library is None:
        parser.error("Existing database and Release shared library are required")
    compiler = shutil.which(os.environ.get("CXX", "c++"))
    if not compiler:
        parser.error("A C++ compiler is required (set CXX to its executable)")
    out = (args.out or ROOT / "auto_test/results" / (
        "paper_forced_order_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    )).resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("DUCKDB_OY") or key == "DUCKDB_SJ_KERNEL_TRACE":
            env.pop(key)
    executable = out / "forced_order"
    compile_command = [compiler, "-std=c++17", "-O2", "-I", str(ROOT / "src/include"),
                       str(HERE / "forced_order.cpp"), "-L", str(library.parent), "-lduckdb",
                       "-Wl,-rpath," + str(library.parent), "-o", str(executable)]
    with (out / "build.stdout.txt").open("w") as stdout, (out / "build.stderr.txt").open("w") as stderr:
        subprocess.run(compile_command, check=True, stdout=stdout, stderr=stderr, env=env, timeout=120)
    shutil.copyfile(query, out / "query.sql")
    shutil.copyfile(HERE / "forced_order.cpp", out / "forced_order.cpp")
    shutil.copyfile(Path(__file__), out / "run_forced_order.py")
    metadata = {"database": str(db), "database_size": db.stat().st_size,
                "database_mtime_ns": db.stat().st_mtime_ns, "library": str(library),
                "library_sha256": sha256(library), "source_sha256": sha256(HERE / "forced_order.cpp"),
                "query_sha256": sha256(query), "platform": platform.platform(),
                "threads": args.threads, "runs": args.runs, "compile_command": compile_command,
                "method": "Bare original SELECT; full exact result multiset; C++ SendQuery/Fetch timing "
                          "includes planning and result drain, excludes row serialization. Two fresh-process "
                          "batches per mode, reversed mode order in batch 2, two warm-ups per batch.",
                "forced_settings": "outer_yan,join_order,unused_columns disabled; process-local pre-optimizer "
                                   "runs filter pushdown + OuterYan Pre/DP/Post; customer-first mode rotates "
                                   "only the reduced associative OT; final grouping verified on every query.",
                "modes": {}}
    (out / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")

    def run(mode, action, runs=1, suffix=""):
        artifact = out / (mode + {"explain": ".plan.txt", "correctness": ".rows.tsv",
                                 "timing": f".timing{suffix}.json", "profile": ".profile.json"}[action])
        command = [str(executable), str(db), str(query), mode, action, str(runs), str(args.threads), str(artifact)]
        result = subprocess.run(command, text=True, capture_output=True, env=env,
                                timeout=120 * (runs + 2) + 30)
        label = mode + "." + action + suffix
        (out / (label + ".stdout.txt")).write_text(result.stdout)
        (out / (label + ".stderr.txt")).write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(f"{label} failed: {result.stderr[:2000]}")
        data = json.loads(result.stdout)
        if data["verified_plans"] < 1:
            raise RuntimeError(f"No final plan verified: {label}")
        if action == "timing":
            artifact.write_text(json.dumps(data, indent=2) + "\n")
        return data

    baseline = None
    for mode in MODES:
        run(mode, "explain")
        result = run(mode, "correctness")
        records = sorted((out / f"{mode}.rows.tsv").read_bytes().splitlines(keepends=True))
        if baseline is None:
            baseline = records
        if records != baseline:
            raise RuntimeError(f"{mode} differs from OFF; all outputs retained in {out}")
        if result["rows"] != len(records):
            raise RuntimeError("Unexpected newline in a result value; this runner expects the fixed TPC-H query")
        metadata["modes"][mode] = {"rows": result["rows"], "correctness": "PASS",
                                   "multiset_sha256": hashlib.sha256(b"".join(records)).hexdigest(),
                                   "seconds": []}
        print(f"{mode}: plan verified; exact multiset PASS ({result['rows']} rows)", flush=True)
    del baseline, records

    counts = [(args.runs + 1) // 2, args.runs // 2]
    for batch, count in enumerate(counts, 1):
        for mode in MODES if batch == 1 else reversed(MODES):
            data = run(mode, "timing", count, str(batch))
            if len(data["seconds"]) != count or data["rows"] != metadata["modes"][mode]["rows"]:
                raise RuntimeError("Incomplete timing batch")
            metadata["modes"][mode]["seconds"].extend(data["seconds"])
    for mode, result in metadata["modes"].items():
        result["median_seconds"] = statistics.median(result["seconds"])
        run(mode, "profile")
        profile = json.loads((out / f"{mode}.profile.json").read_text())
        pair = ("customer", "orders") if mode == "sj_customer_first" else ("orders", "lineitem")
        result.update(inspect_profile(profile, pair))
        if mode.startswith("sj_") and result["sj_probe_count"] != 3:
            raise RuntimeError("Missing semi-join probes in executed physical plan")
    if db.stat().st_size != metadata["database_size"] or db.stat().st_mtime_ns != metadata["database_mtime_ns"]:
        raise RuntimeError("Source database changed during experiment")
    off_median = metadata["modes"]["off"]["median_seconds"]
    for result in metadata["modes"].values():
        result["speedup_off_over_mode"] = off_median / result["median_seconds"]
    (out / "result.json").write_text(json.dumps(metadata, indent=2) + "\n")
    write_csv_results(out, metadata)
    lines = ["# Forced customer–orders experiment", "", f"Threads: {args.threads}; timed runs: {args.runs}.",
             "", "Every mode executes the original SELECT and returns the same exact multiset.",
             "", "| Mode | First real join | Median ms | OFF / mode | Intermediate rows | Real-join input rows |",
             "|---|---|---:|---:|---:|---:|"]
    for mode, result in metadata["modes"].items():
        pair = "customer–orders" if mode == "sj_customer_first" else "orders–lineitem"
        lines.append(f"| {mode} | {pair} | {1000 * result['median_seconds']:.3f} | "
                     f"{result['speedup_off_over_mode']:.3f} | {result['nonroot_intermediate_rows']} | "
                     f"{result['real_join_input_rows']} |")
    lines += ["", metadata["method"], "", "Forced modes are diagnostic overrides, not default OuterYan selection.",
              "Both sj_* modes use identical reducers and disabled optimizers; only the requested OT grouping differs. "
              "Lowering can consequently change join kinds and build/probe orientation.",
              "controlled_off uses the same disabled-optimizer list without OuterYan reduction.",
              "The native off/on modes keep their normal settings. All five modes use the same library and data.",
              "", "Source database is opened read-only. Raw results are SQL-literal TSV, not import-ready TPC-H tables.",
              "Full profiles, EXPLAIN plans, timing samples, hashes and commands are retained next to this report."]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nArtifacts: {out}")


def write_csv_results(out, metadata):
    with (out / "timing_samples.csv").open("w", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(("mode", "sample", "seconds", "milliseconds"))
        for mode, result in metadata["modes"].items():
            for index, seconds in enumerate(result["seconds"], 1):
                writer.writerow((mode, index, seconds, seconds * 1000))
    with (out / "summary.csv").open("w", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(("mode", "correctness", "rows", "median_ms", "speedup_off_over_mode",
                         "nonroot_intermediate_rows", "real_join_input_rows", "multiset_sha256"))
        for mode, result in metadata["modes"].items():
            writer.writerow((mode, result["correctness"], result["rows"], result["median_seconds"] * 1000,
                             result["speedup_off_over_mode"], result["nonroot_intermediate_rows"],
                             result["real_join_input_rows"], result["multiset_sha256"]))


if __name__ == "__main__":
    main()
