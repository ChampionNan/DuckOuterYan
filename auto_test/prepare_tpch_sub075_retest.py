#!/usr/bin/env python3
"""Independent predicate pilots for three TPC-H queries below 0.75x.

Join expressions, projections and aggregates are fixed. Input predicates are
duplicated, never moved out of the null-rejecting outer WHERE. Narrower date
windows change the workload and are labelled separately from equivalent rewrites.
"""
import argparse
from collections import defaultdict
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile

from benchmark_corpus import count_base_relations, read_manifest, sql_fingerprint
from prepare_slow_five_retest import digest, explain, local_timing, query_json
from verify_custdist_retest import multiset, run

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "auto_test/outerjoin_benchmark/revisions/pre_plan_cohort_20261014/benchmark"
REVISION = "tpch-sub075-predicate-20261015"
SPECS = (
    ("Q-H-LD-36", "join__tpch__tuning_20261012_q_h_ld_05__sqlstorm_tpch_17751__left_deep__rfi__e00f7290__sel_high",
     "103a42b0d9a832a98419f2dfdef09f8bc09a4ebae1d3d1907c473f39b18fe251", "lineitem", "l", (720, 480)),
    ("A-H-RD-10", "aggregate__tpch__tpch_q08_market_share__right_deep__flrif__7d16aaba__sel_low__grouped_count",
     "b9ab48bb1075ecb98a866a030d3968aff6c90fdbacef91a3d700d8c90d521b55", "orders", "o", (48, 24)),
    ("A-H-RD-11", "aggregate__tpch__tpch_q08_market_share__right_deep__flrif__7d16aaba__sel_medium__grouped_count",
     "50fdfc86d43cb9378b26abb0cfaddd8e1219266bf0cf2f52b6d48f02e232cd1e", "orders", "o", (480, 240)),
)
BANDS = {"low": (0, .05, "false", "false"),
         "medium": (.05, .4, "true", "false"),
         "high": (.4, .6, "true", "true")}


def with_input_filter(sql, predicate, table, alias):
    leaf = "(SELECT * FROM {} WHERE {}) {}".format(table, predicate.replace(alias + ".", ""), alias)
    target = table + " " + alias
    if sql.count(target) != 1:
        raise ValueError("Expected exactly one input leaf: " + target)
    return sql.replace(target, leaf, 1)


def entries():
    originals = {r["query_id"]: r for r in read_manifest(SOURCE / "manifest.csv")}
    result = []
    for short, query, sha, table, alias, windows in SPECS:
        old = originals[query]
        sql = (SOURCE / old["path"]).read_text()
        if digest(SOURCE / old["path"]) != sha or old["content_sha256"] != sha:
            raise ValueError("Frozen source changed: " + short)
        predicate = old["selectivity_predicate"]
        if sql.count(predicate) != 1:
            raise ValueError("Expected one outer predicate")
        variants = [("original", predicate, old["semantic_tier"], False),
                    ("input", predicate, old["semantic_tier"], True)]
        for days in windows:
            if table == "lineitem":
                end = date(1997, 12, 31)
                start = end - timedelta(days=days - 1)
                tier = "medium"
            else:
                start = date(1995, 1, 1)
                end = start + timedelta(days=days - 1)
                tier = old["semantic_tier"]
            narrowed = "{} BETWEEN DATE '{}' AND DATE '{}'".format(old["selectivity_anchor"], start, end)
            variants.append(("input_d" + str(days), narrowed, tier, True))
        # Keep the failed input-placement probes as diagnostics, but time a
        # predeclared date-window shortlist on CPU9 rather than repeat them.
        if table == "lineitem":
            calendars = [("where_d720", date(1997, 12, 31) - timedelta(days=719), 720, "medium"),
                         ("where_d360", date(1997, 12, 31) - timedelta(days=359), 360, "medium"),
                         ("where_d180", date(1996, 12, 31) - timedelta(days=179), 180, "medium")]
        elif short == "A-H-RD-10":
            calendars = [("where_d110_1995", date(1995, 1, 1), 110, "low"),
                         ("where_d110_1997", date(1997, 1, 1), 110, "low"),
                         ("where_d110_1992", date(1992, 1, 1), 110, "low")]
        else:
            calendars = [("where_d930_1995", date(1995, 1, 1), 930, "medium"),
                         ("where_d930_1992", date(1992, 1, 1), 930, "medium"),
                         ("where_d480_1995", date(1995, 1, 1), 480, "medium")]
        for tag, start, days, tier in calendars:
            current = "{} BETWEEN DATE '{}' AND DATE '{}'".format(
                old["selectivity_anchor"], start, start + timedelta(days=days - 1))
            variants.append((tag, current, tier, False))
        for tag, current, tier, input_filter in variants:
            content = sql.replace(predicate, current, 1)
            if input_filter:
                content = with_input_filter(content, current, table, alias)
            content = content.replace("-- selectivity: " + old["semantic_tier"] + ";",
                                      "-- selectivity: " + tier + ";", 1)
            identifier = query.replace("__sel_" + old["semantic_tier"], "__sel_" + tier)
            identifier += "__sub075_20261015_" + tag
            lo, hi, lc, uc = BANDS[tier]
            row = dict(old, query_id=identifier, path="tpch/" + identifier + ".sql",
                       corpus_revision=REVISION, content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                       sql_fingerprint=sql_fingerprint(content, "tpch"),
                       selectivity_predicate=current, semantic_tier=tier, selectivity_tier="sel_" + tier,
                       target_min_fraction=str(lo), target_max_fraction=str(hi),
                       target_min_inclusive=lc, target_max_inclusive=uc,
                       pilot_source_query=query, pilot_source_sha256=sha, pilot_short_id=short,
                       pilot_table=table, pilot_alias=alias, pilot_variant=tag,
                       pilot_role="original_control" if tag == "original" else "candidate",
                       pilot_run_group="sf50_shortlist" if tag == "original" or tag.startswith("where_") else "local_diagnostic",
                       equivalent_to_source="true" if current == predicate else "false",
                       input_filter_placement="base input plus retained outer WHERE" if input_filter else "outer WHERE",
                       qualification_status="PENDING_CPU9_MEASUREMENT", qualification_min_speedup="0.75",
                       parameter_policy="Independent predicate pilot; narrower dates change workload; no automatic promotion")
            for key in ("target_fraction", "calibration_rows", "calibration_qualified_rows",
                        "calibration_fraction", "calibration_in_range"):
                row[key] = ""
            if count_base_relations(content) != int(old["relation_count"]):
                raise ValueError("Input rewrite changed base relation count")
            result.append((row, content))
    if len({r["sql_fingerprint"] for r, _ in result}) != len(result):
        raise ValueError("Duplicate pilot SQL")
    return result


def materialize(output):
    data = entries()
    output.mkdir(parents=True, exist_ok=False)
    (output / "tpch").mkdir()
    for row, sql in data:
        (output / row["path"]).write_text(sql)
    with (output / "manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(data[0][0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(row for row, _ in data)
    (output / "queries.txt").write_text("".join(row["path"] + "\n" for row, _ in data))
    (output / "protocol.json").write_text(json.dumps(dict(
        revision=REVISION, source_queries=[q for _, q, *_ in SPECS], target_speedup=0.75,
        active_benchmark_modified=False, optimizer_modified=False,
        equivalent_rewrites="Duplicate the original unary predicate at its table input; retain the outer WHERE",
        new_workload_variants="Calendar ranges with explicit tier labels and measured base-table selectivity; the SQLStorm slot narrows to medium, Q8 slots stay within their low/medium bands",
        definitions=21, sf50_trials=12,
        shortlist="Three original controls plus nine WHERE date-window variants; input-subquery probes remain local diagnostics",
        protocol="CPU9 SF50, 32 threads, normal gate, five timed runs per side, median, 600 seconds per statement",
        correctness="Bare-query ON/OFF and input-rewrite equivalence on a tiny adversarial fixture; no full SF50 comparison",
        promotion="Require an actual OuterYan selection and complete median timings >=0.75x; preserve all observations"
    ), indent=2) + "\n")
    print("Prepared {} pilot queries: {}".format(len(data), output), flush=True)


def validate(args):
    binary, database = args.bin.resolve(), args.db.resolve()
    data = entries()
    if read_manifest(args.corpus / "manifest.csv") != [r for r, _ in data]:
        raise ValueError("Pilot manifest differs from generator")
    for row, sql in data:
        if (args.corpus / row["path"]).read_text() != sql:
            raise ValueError("Pilot SQL differs from generator")
    counts = query_json(binary, database, "SELECT (SELECT count(*) FROM orders) AS orders, "
                        "(SELECT count(*) FROM customer) AS customer;")
    if counts != {"orders": 1500000 * args.sf, "customer": 150000 * args.sf}:
        raise ValueError("TPC-H scale mismatch: " + repr(counts))
    groups, fractions = defaultdict(list), {}
    for row, _ in data:
        groups[(row["pilot_table"], row["pilot_alias"])].append(row)
    for (table, alias), rows in groups.items():
        counts = query_json(binary, database, "SELECT count(*) AS n, " + ", ".join(
            "count(*) FILTER (WHERE {}) AS q{}".format(r["selectivity_predicate"].replace(alias + ".", ""), i)
            for i, r in enumerate(rows)) + " FROM " + table + ";")
        for i, row in enumerate(rows):
            fraction = counts["q" + str(i)] / counts["n"]
            actual_tier = "low" if 0 < fraction < .05 else "medium" if .05 <= fraction < .4 else "high" if .4 <= fraction <= .6 else "invalid"
            if actual_tier != row["semantic_tier"]:
                raise ValueError("Unexpected selectivity tier: " + row["query_id"])
            fractions[row["query_id"]] = dict(rows=counts["n"], qualified_rows=counts["q" + str(i)], fraction=fraction)
    info = database.stat()
    signature = json.dumps([str(database), info.st_size, info.st_mtime_ns], separators=(",", ":"))
    audit = dict(database=str(database), database_signature=hashlib.sha256(signature.encode()).hexdigest(),
                 binary_sha256=digest(binary), scale=args.sf, threads=args.threads,
                 active_benchmark_modified=False, candidates=[])
    original = {r["pilot_source_query"]: s for r, s in data if r["pilot_role"] == "original_control"}
    with tempfile.TemporaryDirectory(prefix="tpch-sub075-correctness-") as temporary:
        fixture = Path(temporary) / "tiny.duckdb"
        extension = binary.parent / "extension/tpch/tpch.duckdb_extension"
        run(binary, fixture, "LOAD '{}'; CALL dbgen(sf=0.001);".format(str(extension).replace("'", "''")))
        run(binary, fixture, "ALTER TABLE orders ALTER COLUMN o_orderdate DROP NOT NULL; "
            "ALTER TABLE lineitem ALTER COLUMN l_shipdate DROP NOT NULL; "
            "INSERT INTO orders SELECT * REPLACE (900001 AS o_orderkey, 900001 AS o_custkey, DATE '1995-01-03' AS o_orderdate) FROM orders LIMIT 1; "
            "INSERT INTO orders SELECT * REPLACE (900002 AS o_orderkey, NULL AS o_orderdate) FROM orders LIMIT 1; "
            "INSERT INTO lineitem SELECT * REPLACE (900001 AS l_orderkey, DATE '1997-12-01' AS l_shipdate) FROM lineitem LIMIT 1; "
            "INSERT INTO lineitem SELECT * REPLACE (900002 AS l_orderkey, NULL AS l_shipdate) FROM lineitem LIMIT 1; "
            "INSERT INTO lineitem SELECT * REPLACE (900003 AS l_orderkey, 900003 AS l_partkey) FROM lineitem LIMIT 1; "
            "INSERT INTO lineitem SELECT * FROM lineitem LIMIT 1;")
        for row, sql in data:
            off = multiset(binary, fixture, sql, False)
            if off != multiset(binary, fixture, sql, True) or not off:
                raise ValueError("Bare-query ON/OFF mismatch or empty fixture: " + row["query_id"])
            reference = original[row["pilot_source_query"]]
            old_predicate = next(r["selectivity_predicate"] for r, _ in data
                                 if r["pilot_source_query"] == row["pilot_source_query"] and r["pilot_role"] == "original_control")
            reference = reference.replace(old_predicate, row["selectivity_predicate"], 1)
            if off != multiset(binary, fixture, reference, False):
                raise ValueError("Input-filter equivalence mismatch: " + row["query_id"])
            decision = explain(binary, database, sql, args.threads)
            record = dict(query=row["query_id"], short_query=row["pilot_short_id"], variant=row["pilot_variant"],
                          sql_sha256=row["content_sha256"], calibration=fractions[row["query_id"]],
                          fixture_rows=sum(off.values()), correctness="bare-query multiset equivalence passed",
                          decision=decision)
            if args.local_timing and decision["selected_plan"] == "OUTERYAN":
                record["local_timing_not_cpu9_evidence"] = local_timing(binary, database, sql, args.threads)
            audit["candidates"].append(record)
            print("{} {}: selected={}, selectivity={:.3%}, local_speedup={}".format(
                row["pilot_short_id"], row["pilot_variant"], decision["selected_plan"],
                fractions[row["query_id"]]["fraction"],
                record.get("local_timing_not_cpu9_evidence", {}).get("speedup", "not measured")), flush=True)
    args.audit.write_text(json.dumps(audit, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--out", type=Path)
    action.add_argument("--corpus", type=Path)
    parser.add_argument("--bin", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--sf", type=int)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--local-timing", action="store_true")
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args()
    if args.out:
        materialize(args.out)
    else:
        if not all((args.bin, args.db, args.sf, args.audit)):
            parser.error("Validation requires --bin, --db, --sf and --audit")
        validate(args)


if __name__ == "__main__":
    main()
