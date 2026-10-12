#!/usr/bin/env python3
"""Materialize the reviewed 176-query TPC-H pilot, without promoting it."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent / "outerjoin_benchmark"
ACTIVE = ROOT / "benchmark"
CANDIDATES = ROOT / "candidates/tpch_query_tuning_20261012"
POLICY = ROOT / "sources/tpch_query_tuning_20261012.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def validate_inputs():
    spec = json.loads(POLICY.read_text())
    if digest(ACTIVE / "manifest.csv") != spec["active_manifest_sha256"]:
        raise ValueError("Active manifest changed; rebase the reviewed proposal first")
    active = rows(ACTIVE / "manifest.csv")
    candidates = rows(CANDIDATES / "manifest.csv")
    proposal = rows(CANDIDATES / "proposed_full_manifest.csv")
    if len(active) != 720 or len(candidates) != 31 or len(proposal) != 720:
        raise ValueError("Unexpected reviewed corpus counts")
    replacements = {r["tuning_replaces_query_id"]: r for r in candidates}
    pinned = {p["original"]["query_id"] for p in spec["replacements"]}
    if set(replacements) != pinned or len(replacements) != 31:
        raise ValueError("Replacement targets do not match the pinned policy")
    for old, proposed in zip(active, proposal):
        expected = replacements.get(old["query_id"], old)
        if any(proposed.get(k, "") != v for k, v in expected.items()):
            raise ValueError("Proposal differs from the reviewed one-for-one replacements")
        if old["family"] != "tpch" and old["query_id"] in replacements:
            raise ValueError("Non-TPC-H replacement is not permitted")
    selected = [r for r in proposal if r["family"] == "tpch"]
    if len(selected) != 176 or len({r["query_id"] for r in selected}) != 176:
        raise ValueError("Expected exactly 176 distinct TPC-H queries")
    candidate_ids = {r["query_id"] for r in candidates}
    inputs = []
    for row in selected:
        path = Path(row["path"])
        if path.parts != ("tpch", row["query_id"] + ".sql"):
            raise ValueError("Unexpected SQL path")
        source = CANDIDATES if row["query_id"] in candidate_ids else ACTIVE
        content = (source / path).read_bytes()
        if hashlib.sha256(content).hexdigest() != row["content_sha256"]:
            raise ValueError("SQL hash mismatch: " + row["query_id"])
        inputs.append((row, content))
    return spec, candidates, inputs


def verify_sf50(binary, database, candidates):
    if not database.is_file():
        raise ValueError("Existing SF50 database required; this tool never builds data")

    def query(sql):
        result = subprocess.run(
            [str(binary), "-readonly", str(database), "-json", "-c",
             "SET threads=32; SET disabled_optimizers='outer_yan'; "
             "SET max_execution_time=600000; " + sql],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=630)
        return json.loads(result.stdout)[0]

    counts = query("SELECT (SELECT count(*) FROM orders) AS orders, "
                   "(SELECT count(*) FROM customer) AS customer, "
                   "(SELECT count(*) FROM part) AS part, "
                   "(SELECT count(*) FROM supplier) AS supplier;")
    if counts != dict(orders=75000000, customer=7500000, part=10000000, supplier=500000):
        raise ValueError("Database cardinalities do not match SF50: " + repr(counts))
    print("Confirmed SF50 base-table counts: " + json.dumps(counts), flush=True)
    groups = defaultdict(list)
    for row in candidates:
        groups[row["selectivity_denominator"]].append(row)
    calibration = []
    for denominator, group in sorted(groups.items()):
        fields = ["count(*) AS n"] + [
            "count(*) FILTER (WHERE {}) AS q{}".format(r["selectivity_predicate"], i)
            for i, r in enumerate(group)]
        measured = query("SELECT " + ", ".join(fields) + " FROM " + denominator + ";")
        for i, row in enumerate(group):
            fraction = measured["q" + str(i)] / measured["n"]
            low, high = float(row["target_min_fraction"]), float(row["target_max_fraction"])
            low_ok = fraction >= low if row["target_min_inclusive"] == "true" else fraction > low
            high_ok = fraction <= high if row["target_max_inclusive"] == "true" else fraction < high
            if not (low_ok and high_ok):
                raise ValueError("SF50 selectivity outside reviewed band: " + row["query_id"])
            calibration.append(dict(query_id=row["query_id"], tier=row["semantic_tier"],
                                    rows=measured["n"], qualified=measured["q" + str(i)],
                                    fraction=fraction))
    for tier in ("low", "medium", "high"):
        fractions = [r["fraction"] for r in calibration if r["tier"] == tier]
        print("SF50 {}: n={}, fraction={:.4%}..{:.4%}".format(
            tier, len(fractions), min(fractions), max(fractions)), flush=True)
    return dict(database=str(database), binary=str(binary), binary_sha256=digest(binary),
                scale=50, table_counts=counts, candidate_calibration=calibration)


def materialize(output, inputs, spec, verification=None):
    output.mkdir(parents=True, exist_ok=False)
    (output / "tpch").mkdir()
    records = []
    for row, content in inputs:
        (output / row["path"]).write_bytes(content)
        records.append(dict(row, corpus_revision=spec["revision"] + "-full-pilot"))
    fields = list(dict.fromkeys(k for row in records for k in row))
    with (output / "manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    (output / "queries.txt").write_text("".join(r["path"] + "\n" for r in records))
    audit = dict(active_manifest_sha256=spec["active_manifest_sha256"],
                 policy_sha256=digest(POLICY), query_count=176, candidate_count=31,
                 unchanged_count=145, active_benchmark_modified=False,
                 family_counts=dict(Counter(r["family"] for r in records)),
                 database_verification=verification)
    (output / "pilot_provenance.json").write_text(json.dumps(audit, indent=2) + "\n")
    print("Prepared 176 TPC-H queries (31 candidates + 145 unchanged) at " + str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bin", type=Path)
    parser.add_argument("--db", type=Path)
    args = parser.parse_args()
    if bool(args.bin) != bool(args.db):
        parser.error("--bin and --db must be supplied together for SF50 verification")
    output = args.out.resolve()
    if output.exists():
        parser.error("Output already exists; choose a fresh pilot directory")
    spec, candidates, inputs = validate_inputs()
    verified = verify_sf50(args.bin.resolve(), args.db.resolve(), candidates) if args.bin else None
    materialize(output, inputs, spec, verified)


if __name__ == "__main__":
    main()
