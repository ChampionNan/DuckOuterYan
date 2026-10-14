#!/usr/bin/env python3
"""Selectivity-only pilots for three slow slots; never promote automatically.

Lower selectivities are intentionally allowed. The candidate metadata and SQL
identifier use the actual target band, not the original slot's band.
"""
import argparse
from collections import Counter
import csv
from datetime import date, timedelta
import hashlib
from pathlib import Path

import prepare_slow_five_retest as common

REVISION = "slow-three-selectivity-20261014"
SPECS = common.SPECS[2:]
BANDS = {"low": (0, .05, "false", "false"),
         "medium": (.05, .4, "true", "false"),
         "high": (.4, .6, "true", "true")}
WINDOWS = ((60, "early", "low"), (90, "early", "low"),
           (240, "early", "medium"), (480, "early", "medium"),
           (240, "late", "medium"), (480, "late", "medium"))


def variants(short, anchor):
    if short == "A-H-B-07":
        result = []
        for days, position, band in WINDOWS:
            start, end = date(1992, 1, 1), date(1998, 8, 2)
            if position == "early":
                end = start + timedelta(days=days - 1)
            else:
                start = end - timedelta(days=days - 1)
            result.append((f"d{days}_{position}", band,
                           f"{anchor} BETWEEN DATE '{start}' AND DATE '{end}'"))
        return result
    if short == "A-J-RD-05":
        return [("y2009", "medium", f"{anchor} >= 2009"),
                ("y2013", "low", f"{anchor} >= 2013")] + [
                    (f"y{lo}_{hi}", "medium", f"{anchor} BETWEEN {lo} AND {hi}")
                    for lo, hi in ((1990, 2000), (1900, 1998), (1970, 2003), (1995, 2008))]
    if short == "A-J-B-07":
        return [("y2003_2011", "high", f"{anchor} BETWEEN 2003 AND 2011")]
    raise ValueError("Unknown pilot slot: " + short)


def assemble(active=common.ACTIVE):
    with (active / "manifest.csv").open(newline="") as handle:
        originals = {r["query_id"]: r for r in csv.DictReader(handle)}
    entries, seen = [], set()
    for short, query, expected in SPECS:
        original = originals[query]
        path = active / original["path"]
        if common.digest(path) != expected or original["content_sha256"] != expected:
            raise ValueError("Frozen source SQL changed: " + short)
        source, old = path.read_text(), original["selectivity_predicate"]
        if source.count(old) != 1:
            raise ValueError("Expected exactly one predicate: " + short)
        choices = [("original", original["semantic_tier"], old)] + variants(short, original["selectivity_anchor"])
        for tag, band, predicate in choices:
            sql = source.replace(old, predicate, 1)
            fingerprint = common.sql_fingerprint(sql, original["family"])
            if fingerprint in seen or sql.replace(predicate, old, 1) != source:
                raise ValueError("Duplicate candidate or non-predicate SQL change")
            seen.add(fingerprint)
            identifier = query.replace("__sel_" + original["semantic_tier"], "__sel_" + band)
            identifier += "__slow3_20261014_" + tag
            lo, hi, lower_closed, upper_closed = BANDS[band]
            row = dict(original, query_id=identifier, path=original["family"] + "/" + identifier + ".sql",
                       content_sha256=hashlib.sha256(sql.encode()).hexdigest(), sql_fingerprint=fingerprint,
                       selectivity_predicate=predicate, semantic_tier=band, selectivity_tier="sel_" + band,
                       target_min_fraction=str(lo), target_max_fraction=str(hi),
                       target_min_inclusive=lower_closed, target_max_inclusive=upper_closed,
                       corpus_revision=REVISION, pilot_short_id=short, pilot_source_query=query,
                       pilot_source_sha256=expected, pilot_source_tier=original["semantic_tier"],
                       pilot_variant=tag, pilot_role="original_control" if tag == "original" else "candidate",
                       qualification_status="PENDING_CPU9_MEASUREMENT", qualification_min_speedup="0.7",
                       qualification_min_runtime_s="0",
                       parameter_policy="Selectivity-only exploration; lower bands allowed and explicitly labelled. "
                                        "Performance-conditioned candidates; no automatic promotion.")
            for field in ("target_fraction", "calibration_rows", "calibration_qualified_rows",
                          "calibration_fraction", "calibration_in_range"):
                row[field] = ""
            entries.append((row, sql))
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bin", type=Path, required=True)
    parser.add_argument("--tpch-db", type=Path, required=True)
    parser.add_argument("--job-db", type=Path, required=True)
    parser.add_argument("--tpch-sf", type=int, default=50)
    parser.add_argument("--threads", type=int, default=32)
    parser.add_argument("--local-check", action="store_true", help="Compare bare ON/OFF outputs on supplied local DBs")
    parser.add_argument("--local-timing", action="store_true", help="Directional diagnostics, not CPU9 acceptance")
    args = parser.parse_args()
    if args.out.exists() or args.threads < 1 or args.tpch_sf < 1:
        parser.error("Use a fresh output directory, positive threads and scale")
    binary = args.bin.resolve()
    databases = {"tpch": args.tpch_db.resolve(), "job": args.job_db.resolve()}
    if not binary.is_file() or not all(p.is_file() for p in databases.values()):
        parser.error("Existing Release binary and database files required")
    entries = assemble()
    counts = common.calibrate(binary, databases, entries, args.tpch_sf)
    audit = dict(revision=REVISION, query_count=len(entries), controls=3, candidates=len(entries) - 3,
                 tpch_scale=args.tpch_sf, tpch_counts=counts, threads=args.threads,
                 binary_sha256=common.digest(binary), active_manifest_sha256=common.digest(common.ACTIVE / "manifest.csv"),
                 active_benchmark_modified=False, optimizer_modified=False,
                 selectivity_counts=dict(Counter(r["semantic_tier"] for r, _ in entries)),
                 acceptance="CPU9 SF50/32 threads; five unprofiled post-warmup executions per engine; "
                            "median ratio >= 0.7, both engines completed, OuterYan selected. "
                            "Fallback 1x is not an improvement. No automatic promotion.", decisions=[])
    for row, sql in entries:
        database = databases[row["family"]]
        decision = common.explain(binary, database, sql, args.threads)
        record = dict(query_id=row["query_id"], short_query=row["pilot_short_id"],
                      variant=row["pilot_variant"], tier=row["semantic_tier"],
                      fraction=float(row["calibration_fraction"]), decision=decision)
        if args.local_check:
            record["local_correctness"] = dict(
                rows=common.bare_equivalence(binary, database, sql, args.threads),
                status="equivalent", cpu9_correctness_claim=False)
        if args.local_timing:
            record["local_timing_not_cpu9_evidence"] = common.local_timing(binary, database, sql, args.threads)
        audit["decisions"].append(record)
        print(f"{row['pilot_short_id']} {row['pilot_variant']}: tier={row['semantic_tier']} "
              f"fraction={record['fraction']:.4%} selected={decision['selected_plan']} "
              f"local_ratio={record.get('local_timing_not_cpu9_evidence', {}).get('speedup', 'not measured')}", flush=True)
    common.materialize(args.out.resolve(), entries, audit)


if __name__ == "__main__":
    main()
