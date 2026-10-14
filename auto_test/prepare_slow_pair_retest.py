#!/usr/bin/env python3
"""Stage two original queries and six selectivity-only candidates, without promotion."""
import argparse
import csv
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from benchmark_corpus import sql_fingerprint

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "auto_test/outerjoin_benchmark/benchmark"
REVISION = "slow-pair-selectivity-20261014"
MANIFEST_SHA = "a8813f1c94aa3ad9fab60e7b107bbb8e598d3d134830298b51244a307035d5d4"
SPECS = (
    ("A-J-B-04", "job", "aggregate__job__sqlstorm_job_11914__bushy__ilrff__9a0ef4e8__sel_medium__grouped_count",
     "cd908a47ed290e84c73015c1c738dae244764e4538637d8aec0e4e5d57ce1ff8"),
    ("G-H-LD-03", "tpch", "graph__tpch__th_real_custdist__left_deep__lrf__65a983cc__sel_medium",
     "0c14c5c3d847a2a7ff6583da4e7bac34ae3d3f708a18afd0e035e97b6e7d684a"),
)
UNSAFE_ENV = ("DUCKDB_OY_FORCE_CANDIDATE", "DUCKDB_OY_SIMPLIFY_SCAN_FILTERS",
              "DUCKDB_OYTRACE", "DUCKDB_OY_PROFILE_TRACE", "DUCKDB_SJ_KERNEL_TRACE")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def variants(family):
    if family == "job":
        return [("y" + str(year), "t.production_year >= " + str(year)) for year in (2010, 2011, 2012)]
    end = date(1996, 3, 9)
    return [("d" + str(days), "orders.o_orderdate BETWEEN DATE '{}' AND DATE '{}'".format(
        end - timedelta(days=days - 1), end)) for days in (366, 240, 180)]


def assemble(active=ACTIVE):
    if digest(active / "manifest.csv") != MANIFEST_SHA:
        raise ValueError("Active manifest changed; review/rebase the two-query pilot first")
    with (active / "manifest.csv").open(newline="") as handle:
        records = {r["query_id"]: r for r in csv.DictReader(handle)}
    result = []
    for short_id, family, original_id, expected_hash in SPECS:
        original = records[original_id]
        source = active / original["path"]
        if digest(source) != expected_hash or original["content_sha256"] != expected_hash:
            raise ValueError("Source SQL changed: " + original_id)
        sql = source.read_text()
        old_predicate = original["selectivity_predicate"]
        if sql.count(old_predicate) != 1 or original["semantic_tier"] != "medium":
            raise ValueError("Expected exactly one frozen medium-tier predicate")
        for tag, predicate in [("original", old_predicate)] + variants(family):
            row = dict(original)
            candidate = tag != "original"
            content = sql.replace(old_predicate, predicate, 1) if candidate else sql
            if content.replace(predicate, old_predicate, 1) != sql:
                raise ValueError("Non-predicate SQL modification")
            query_id = original_id if not candidate else original_id + "__pilot_20261014_" + tag
            row.update(query_id=query_id, path=family + "/" + query_id + ".sql",
                       corpus_revision=REVISION, selectivity_predicate=predicate,
                       content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                       sql_fingerprint=sql_fingerprint(content, family),
                       pilot_source_query=original_id, pilot_source_sha256=expected_hash,
                       pilot_short_id=short_id, pilot_variant=tag,
                       pilot_role="candidate" if candidate else "original_control",
                       qualification_status="PENDING_CPU9_MEASUREMENT",
                       qualification_min_speedup="0.7", qualification_min_runtime_s="0",
                       parameter_policy="selectivity-only pilot; no automatic promotion")
            if candidate:
                for key in ("target_fraction", "calibration_rows", "calibration_qualified_rows",
                            "calibration_fraction", "calibration_in_range"):
                    row[key] = ""
            result.append((row, content))
    return result


def sql_result(binary, database, sql):
    env = {k: v for k, v in os.environ.items() if k not in UNSAFE_ENV}
    proc = subprocess.run([str(binary), "-no-init", "-bail", "-readonly", str(database), "-json", "-c",
                           "SET threads=32; SET disabled_optimizers='outer_yan'; "
                           "SET max_execution_time=600000; " + sql],
                          capture_output=True, universal_newlines=True, timeout=630, env=env)
    if proc.returncode:
        raise ValueError(proc.stderr)
    return json.loads(proc.stdout)[0]


def verify(binary, databases, entries, expected_sf):
    for database in databases.values():
        if not database.is_file():
            raise ValueError("Existing database required: " + str(database))
    counts = sql_result(binary, databases["tpch"],
                        "SELECT (SELECT count(*) FROM orders) AS orders, "
                        "(SELECT count(*) FROM customer) AS customer;")
    if counts != {"orders": 1500000 * expected_sf, "customer": 150000 * expected_sf}:
        raise ValueError("TPC-H scale mismatch: " + repr(counts))
    audit = {"tpch_scale": expected_sf, "tpch_counts": counts, "binary_sha256": digest(binary),
             "databases": {k: str(v) for k, v in databases.items()}, "decisions": []}
    for family in ("job", "tpch"):
        group = [(row, sql) for row, sql in entries if row["family"] == family]
        table, anchor = ("title t", "t.production_year") if family == "job" else ("orders", "orders.o_orderdate")
        fields = ["count(*) AS total"] + [
            "count(*) FILTER (WHERE {}) AS q{}".format(row["selectivity_predicate"], i)
            for i, (row, _) in enumerate(group)]
        calibration = sql_result(binary, databases[family], "SELECT " + ", ".join(fields) + " FROM " + table)
        original_fraction = calibration["q0"] / calibration["total"]
        for i, (row, sql) in enumerate(group):
            fraction = calibration["q" + str(i)] / calibration["total"]
            if not 0.05 <= fraction < 0.40 or (i > 0 and fraction >= original_fraction):
                raise ValueError("Candidate must reduce selectivity within the medium band")
            row.update(calibration_rows=str(calibration["total"]),
                       calibration_qualified_rows=str(calibration["q" + str(i)]),
                       calibration_fraction=str(fraction), calibration_in_range="true",
                       target_fraction=str(fraction), selectivity_denominator=table,
                       selectivity_anchor=anchor)
            # EXPLAIN reads the normal optimizer decision; never force a candidate.
            with tempfile.TemporaryDirectory(prefix="slow-pair-explain-") as temporary:
                trace = Path(temporary) / "trace.txt"
                env = {k: v for k, v in os.environ.items() if k not in UNSAFE_ENV}
                env["DUCKDB_OYTRACE"] = str(trace)
                proc = subprocess.run([str(binary), "-no-init", "-bail", "-readonly", str(databases[family])],
                    input="SET threads=32; SET disabled_optimizers=''; EXPLAIN (FORMAT JSON) " + sql,
                    capture_output=True, universal_newlines=True, timeout=60, env=env)
                if proc.returncode:
                    raise ValueError(proc.stderr)
                lines = [line for line in trace.read_text().splitlines() if line.startswith("[OY_DECISION]")]
                if not lines:
                    raise ValueError("Missing optimizer decision")
                decision = dict(re.findall(r"(\w+)=([^\s]+)", lines[-1]))
            audit["decisions"].append(dict(query_id=row["query_id"], fraction=fraction, decision=decision))
            print("{} {}: fraction={:.4%}; selected={}; R1={}; R2={}".format(
                row["pilot_short_id"], row["pilot_variant"], fraction, decision["selected_plan"],
                decision.get("executed_round1_pairs"), decision.get("executed_round2_pairs")), flush=True)
    return audit


def materialize(output, entries, verification):
    output.mkdir(parents=True, exist_ok=False)
    for row, content in entries:
        path = output / row["path"]
        path.parent.mkdir(exist_ok=True)
        path.write_text(content)
    fields = list(dict.fromkeys(key for row, _ in entries for key in row))
    with (output / "manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(row for row, _ in entries)
    (output / "queries.txt").write_text("".join(row["path"] + "\n" for row, _ in entries))
    (output / "pilot_provenance.json").write_text(json.dumps({
        "revision": REVISION, "active_manifest_sha256": MANIFEST_SHA,
        "active_benchmark_modified": False, "optimizer_modified": False,
        "queries": len(entries), "original_controls": 2, "candidates": 6,
        "target_speedup": 0.7, "acceptance_requires": "OUTERYAN selected and both measured without timeout",
        "database_verification": verification,
    }, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bin", type=Path, required=True)
    parser.add_argument("--tpch-db", type=Path, required=True)
    parser.add_argument("--job-db", type=Path, required=True)
    parser.add_argument("--tpch-sf", type=int, default=50)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a fresh output directory")
    entries = assemble()
    verification = verify(args.bin.resolve(), {"tpch": args.tpch_db.resolve(), "job": args.job_db.resolve()},
                          entries, args.tpch_sf)
    materialize(args.out.resolve(), entries, verification)
    print("Prepared two controls and six candidates at " + str(args.out.resolve()))


if __name__ == "__main__":
    main()
