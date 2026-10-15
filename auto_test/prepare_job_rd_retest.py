#!/usr/bin/env python3
"""Predicate-only JOB 10a right-deep pilot; never change the active workload.

Earlier narrower year windows retained seven semi-join pairs. These wider
windows test whether increased join work can amortize that overhead. Local
timings are diagnostics only; promotion requires fresh CPU9 measurements.
"""
import argparse
from collections import Counter
import csv
import hashlib
from pathlib import Path

import prepare_slow_five_retest as common

REVISION = "job-rd-selectivity-20261015"
QUERY = "aggregate__job__job_10a_cast_credits__right_deep__rlif__87f83502__sel_medium__grouped_count"
SOURCE_SHA = "50a5191307d0af3414203b6febfd5e60a62ea198a948e1e73762d5a6e8d69c29"
YEARS = (1999, 2001, 2003, 2005, 2006)


def assemble(active=common.ACTIVE):
    with (active / "manifest.csv").open(newline="") as handle:
        original = next(r for r in csv.DictReader(handle) if r["query_id"] == QUERY)
    path = active / original["path"]
    if common.digest(path) != SOURCE_SHA or original["content_sha256"] != SOURCE_SHA:
        raise ValueError("JOB right-deep source changed; rebase the pilot explicitly")
    source, old = path.read_text(), original["selectivity_predicate"]
    if old != "t.production_year >= 2008" or source.count(old) != 1:
        raise ValueError("Expected the original year predicate once")
    choices = [("original", "medium", old)] + [
        ("y" + str(year), "high", "t.production_year >= " + str(year)) for year in YEARS]
    entries = []
    for tag, tier, predicate in choices:
        sql = source.replace(old, predicate, 1)
        if sql.replace(predicate, old, 1) != source:
            raise ValueError("Non-predicate SQL modification")
        sql = sql.replace("-- selectivity: medium;", "-- selectivity: " + tier + ";", 1)
        identifier = QUERY.replace("__sel_medium__", "__sel_" + tier + "__")
        identifier += "__jobrd_20261015_" + tag
        row = dict(original, query_id=identifier, path="job/" + identifier + ".sql",
                   content_sha256=hashlib.sha256(sql.encode()).hexdigest(),
                   sql_fingerprint=common.sql_fingerprint(sql, "job"),
                   selectivity_predicate=predicate, semantic_tier=tier, selectivity_tier="sel_" + tier,
                   target_min_fraction="0.05" if tier == "medium" else "0.4",
                   target_max_fraction="0.4" if tier == "medium" else "0.6",
                   target_min_inclusive="true", target_max_inclusive="false" if tier == "medium" else "true",
                   corpus_revision=REVISION, pilot_source_query=QUERY, pilot_source_sha256=SOURCE_SHA,
                   pilot_short_id="A-J-RD-01", pilot_variant=tag,
                   pilot_role="original_control" if tag == "original" else "candidate",
                   qualification_status="PENDING_CPU9_MEASUREMENT", qualification_min_speedup="0.7",
                   qualification_min_runtime_s="0",
                   parameter_policy="Predicate-only independent pilot; wider year cohorts, actual tiers recorded; "
                                    "CPU9 measurement required; no automatic promotion")
        for field in ("target_fraction", "calibration_rows", "calibration_qualified_rows",
                      "calibration_fraction", "calibration_in_range"):
            row[field] = ""
        entries.append((row, sql))
    if len({r["sql_fingerprint"] for r, _ in entries}) != len(entries):
        raise ValueError("Duplicate pilot SQL")
    return entries


def calibrate(binary, database, entries):
    fields = ["count(*) AS n"] + ["count(*) FILTER (WHERE {}) AS q{}".format(
        row["selectivity_predicate"], i) for i, (row, _) in enumerate(entries)]
    counts = common.query_json(binary, database, "SELECT " + ", ".join(fields) + " FROM title t;")
    if counts["n"] != 2528312:
        raise ValueError("JOB title row count differs from the CPU9 source workload")
    for i, (row, _) in enumerate(entries):
        fraction = counts["q" + str(i)] / counts["n"]
        lo, hi = float(row["target_min_fraction"]), float(row["target_max_fraction"])
        upper = fraction <= hi if row["target_max_inclusive"] == "true" else fraction < hi
        if not lo <= fraction or not upper:
            raise ValueError("Unexpected selectivity tier: " + row["query_id"])
        row.update(target_fraction=str(fraction), calibration_fraction=str(fraction),
                   calibration_rows=str(counts["n"]), calibration_qualified_rows=str(counts["q" + str(i)]),
                   calibration_in_range="true")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bin", type=Path, required=True)
    parser.add_argument("--job-db", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=32)
    parser.add_argument("--local-check", action="store_true")
    parser.add_argument("--local-timing", action="store_true")
    args = parser.parse_args()
    binary, database = args.bin.resolve(), args.job_db.resolve()
    if args.out.exists() or args.threads < 1 or not binary.is_file() or not database.is_file():
        parser.error("A fresh output directory, existing binary/database and positive threads are required")
    entries = assemble()
    counts = calibrate(binary, database, entries)
    audit = dict(revision=REVISION, query_count=len(entries), controls=1, candidates=len(entries) - 1,
                 title_rows=counts["n"], threads=args.threads, database=str(database),
                 binary_sha256=common.digest(binary), active_manifest_sha256=common.digest(common.ACTIVE / "manifest.csv"),
                 active_benchmark_modified=False, optimizer_modified=False,
                 selectivity_counts=dict(Counter(r["semantic_tier"] for r, _ in entries)),
                 acceptance="CPU9, 32 threads, five post-warmup runs per engine, median ratio >=0.7; "
                            "both engines measured, OUTERYAN selected, cost gate enabled; no automatic promotion.",
                 decisions=[])
    for row, sql in entries:
        decision = common.explain(binary, database, sql, args.threads)
        record = dict(query_id=row["query_id"], variant=row["pilot_variant"],
                      fraction=float(row["calibration_fraction"]), decision=decision)
        if args.local_check:
            record["local_correctness"] = dict(rows=common.bare_equivalence(binary, database, sql, args.threads),
                                               status="equivalent", cpu9_correctness_claim=False)
        if args.local_timing:
            record["local_timing_not_cpu9_evidence"] = common.local_timing(binary, database, sql, args.threads)
        audit["decisions"].append(record)
        print("{}: fraction={:.4%}; selected={}; local_ratio={}".format(
            row["pilot_variant"], record["fraction"], decision["selected_plan"],
            record.get("local_timing_not_cpu9_evidence", {}).get("speedup", "not measured")), flush=True)
    common.materialize(args.out.resolve(), entries, audit)
    print("Pilot prepared; active benchmark unchanged: " + str(args.out.resolve()))


if __name__ == "__main__":
    main()
