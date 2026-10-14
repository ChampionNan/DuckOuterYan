#!/usr/bin/env python3
"""One unchanged A-H-B-07 control and six date-window candidates; no promotion."""
import argparse
import csv
from datetime import date, timedelta
import hashlib
from pathlib import Path

import prepare_slow_five_retest as common

QUERY = "aggregate__tpch__tuning_20261012_a_h_b_07__sqlstorm_tpch_25509__bushy__lfilr__92747bc0__sel_high__grouped_count"
SOURCE_HASH = "4fc59a70f9c04bb95fd2fd6546b7dd68d97c84635fa048222007f35d46994761"
WINDOWS = (("d970_early", "1992-01-01", 970),
           ("d1100_early", "1992-01-01", 1100),
           ("d1320_early", "1992-01-01", 1320),
           ("d970_mid1993", "1993-01-01", 970),
           ("d1100_mid1993", "1993-01-01", 1100),
           ("d970_mid1994", "1994-01-01", 970))


def assemble(active=common.ACTIVE):
    with (active / "manifest.csv").open(newline="") as handle:
        original = next(r for r in csv.DictReader(handle) if r["query_id"] == QUERY)
    source = active / original["path"]
    if common.digest(source) != SOURCE_HASH or original["content_sha256"] != SOURCE_HASH:
        raise ValueError("A-H-B-07 source changed")
    sql, anchor, old = source.read_text(), original["selectivity_anchor"], original["selectivity_predicate"]
    if sql.count(old) != 1:
        raise ValueError("Expected exactly one date predicate")
    variants = [("original", old)]
    for name, start, days in WINDOWS:
        end = date.fromisoformat(start) + timedelta(days=days - 1)
        variants.append((name, f"{anchor} BETWEEN DATE '{start}' AND DATE '{end}'"))
    entries, seen = [], set()
    for name, predicate in variants:
        content = sql.replace(old, predicate, 1)
        fingerprint = common.sql_fingerprint(content, "tpch")
        if fingerprint in seen or content.replace(predicate, old, 1) != sql:
            raise ValueError("Duplicate SQL or non-predicate change")
        seen.add(fingerprint)
        query = QUERY + "__ahb07_20261014_" + name
        row = dict(original, query_id=query, path="tpch/" + query + ".sql",
                   content_sha256=hashlib.sha256(content.encode()).hexdigest(), sql_fingerprint=fingerprint,
                   selectivity_predicate=predicate, corpus_revision="ahb07-date-windows-20261014",
                   pilot_source_query=QUERY, pilot_source_sha256=SOURCE_HASH, pilot_short_id="A-H-B-07",
                   pilot_variant=name, pilot_role="original_control" if name == "original" else "candidate",
                   qualification_status="PENDING_CPU9_MEASUREMENT", qualification_min_speedup="0.7",
                   parameter_policy="Date-window-only pilot; preserve the high selectivity band. No automatic promotion.")
        for key in ("target_fraction", "calibration_rows", "calibration_qualified_rows",
                    "calibration_fraction", "calibration_in_range"):
            row[key] = ""
        entries.append((row, content))
    return entries


def calibrate(binary, database, entries, sf):
    counts = common.query_json(binary, database, "SELECT (SELECT count(*) FROM orders) AS orders, "
                               "(SELECT count(*) FROM customer) AS customer;")
    if counts != {"orders": sf * 1500000, "customer": sf * 150000}:
        raise ValueError("TPC-H scale mismatch: " + repr(counts))
    columns = ["count(*) AS n"] + [
        f"count(*) FILTER (WHERE {row['selectivity_predicate'].replace('o.o_orderdate', 'o_orderdate')}) AS q{i}"
        for i, (row, _) in enumerate(entries)]
    result = common.query_json(binary, database, "SELECT " + ", ".join(columns) + " FROM orders;")
    for i, (row, _) in enumerate(entries):
        qualified, total = result[f"q{i}"], result["n"]
        fraction = qualified / total
        if not .4 <= fraction <= .6:
            raise ValueError("Candidate is outside the high band: " + row["pilot_variant"])
        row.update(target_fraction=str(fraction), calibration_rows=str(total),
                   calibration_qualified_rows=str(qualified), calibration_fraction=str(fraction),
                   calibration_in_range="true")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bin", type=Path, required=True)
    parser.add_argument("--tpch-db", type=Path, required=True)
    parser.add_argument("--tpch-sf", type=int, default=50)
    parser.add_argument("--threads", type=int, default=32)
    parser.add_argument("--local-check-db", type=Path)
    parser.add_argument("--local-timing", action="store_true")
    args = parser.parse_args()
    if args.out.exists() or args.threads < 1 or args.tpch_sf < 1:
        parser.error("Use a fresh output directory, positive threads and scale")
    binary, database = args.bin.resolve(), args.tpch_db.resolve()
    if not binary.is_file() or not database.is_file():
        parser.error("An existing Release binary and database are required")
    entries = assemble()
    counts = calibrate(binary, database, entries, args.tpch_sf)
    audit = dict(query_count=len(entries), controls=1, candidates=6, tpch_scale=args.tpch_sf,
                 tpch_counts=counts, threads=args.threads, binary_sha256=common.digest(binary),
                 active_benchmark_modified=False, optimizer_modified=False, decisions=[])
    for row, sql in entries:
        decision = common.explain(binary, database, sql, args.threads)
        record = dict(query_id=row["query_id"], variant=row["pilot_variant"],
                      fraction=float(row["calibration_fraction"]), decision=decision)
        if args.local_check_db:
            record["local_correctness"] = dict(
                rows=common.bare_equivalence(binary, args.local_check_db.resolve(), sql, args.threads),
                status="equivalent", cpu9_correctness_claim=False)
        if args.local_timing:
            record["local_timing_not_cpu9_evidence"] = common.local_timing(binary, database, sql, args.threads)
        audit["decisions"].append(record)
        print(f"{row['pilot_variant']}: fraction={record['fraction']:.4%}; "
              f"selected={decision['selected_plan']}; "
              f"local_ratio={record.get('local_timing_not_cpu9_evidence', {}).get('speedup', 'not measured')}", flush=True)
    common.materialize(args.out.resolve(), entries, audit)


if __name__ == "__main__":
    main()
