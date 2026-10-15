#!/usr/bin/env python3
"""Isolated G-H-LD-05 pilot: filter the remaining semi-join build input.

These are new shipment-date workload variants, not equivalent replacements for
the active query. Each ON/OFF pair executes exactly the same bare SQL. The
input-filter form is checked against the same predicates in an outer WHERE.
"""
import argparse
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile

from benchmark_corpus import count_base_relations, sql_fingerprint
from prepare_custdist_retest import SOURCE_DIR, QUERY, SOURCE_SHA, prepare as previous_entries
from prepare_slow_five_retest import explain, local_timing, query_json
from verify_custdist_retest import multiset, run

REVISION = "custdist-lineitem-pilot-20261015"


def entries():
    previous, control = next((r, s) for r, s in previous_entries()
                             if r["pilot_days"] == "840" and r["pilot_placement"] == "input")
    result = []
    for days in (None, 840, 366, 240):
        predicate = ""
        sql = control
        tag = "control" if days is None else "ship" + str(days)
        if days is not None:
            first = date(1992, 1, 1)
            last = first + timedelta(days=days - 1)
            predicate = "lineitem.l_shipdate BETWEEN DATE '{}' AND DATE '{}'".format(first, last)
            leaf = "(SELECT * FROM lineitem WHERE {}) AS lineitem".format(
                predicate.replace("lineitem.", ""))
            assert sql.count("RIGHT OUTER JOIN lineitem ON") == 1
            sql = sql.replace("RIGHT OUTER JOIN lineitem ON", "RIGHT OUTER JOIN " + leaf + " ON", 1)
            assert sql.rstrip().endswith(";")
            sql = sql.rstrip()[:-1] + "\n  AND " + predicate + ";\n"
            sql = ("-- Independent G-H-LD-05 shipment-date candidate; pending CPU9 measurement.\n"
                   "-- Four relations and LRF expression retained; orders and lineitem input predicates.\n"
                   "-- New predicate changes the workload; not equivalent to the active query.\n" +
                   sql[sql.index("SELECT *"):])
        identifier = QUERY + "__custdist_line_20261015_" + tag
        row = dict(previous, query_id=identifier, path="tpch/" + identifier + ".sql",
                   corpus_revision=REVISION, content_sha256=hashlib.sha256(sql.encode()).hexdigest(),
                   sql_fingerprint=sql_fingerprint(sql, "tpch"), pilot_variant=tag,
                   pilot_role="previous_best_control" if days is None else "candidate",
                   pilot_source_query=QUERY, pilot_source_sha256=SOURCE_SHA,
                   pilot_lineitem_days="" if days is None else str(days),
                   lineitem_selectivity_predicate=predicate,
                   unary_predicates_json=json.dumps({"orders": previous["selectivity_predicate"],
                                                     "lineitem": predicate}, sort_keys=True),
                   equivalent_to_active="true" if days is None else "false",
                   input_filter_placement="orders input and outer WHERE" if days is None
                   else "orders and lineitem inputs, with both outer predicates retained",
                   parameter_policy="Independent two-input selectivity pilot; no optimizer changes or automatic promotion")
        assert count_base_relations(sql) == 4
        assert row["join_vector"] == "LRF"
        assert sql.count("LEFT OUTER JOIN") == sql.count("RIGHT OUTER JOIN") == sql.count("FULL OUTER JOIN") == 1
        result.append((row, sql))
    assert len({r["sql_fingerprint"] for r, _ in result}) == 4
    return result


def materialize(directory):
    data = entries()
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "tpch").mkdir()
    for row, sql in data:
        (directory / row["path"]).write_text(sql)
    with (directory / "manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(data[0][0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(r for r, _ in data)
    (directory / "queries.txt").write_text("".join(r["path"] + "\n" for r, _ in data))
    (directory / "protocol.json").write_text(json.dumps(dict(
        revision=REVISION, source_query=QUERY, source_sha256=SOURCE_SHA, target_speedup=0.75,
        active_benchmark_modified=False, optimizer_modified=False,
        control="Previous equivalent orders-input rewrite at 34.90114% orders selectivity",
        candidates="Additional lineitem shipment-date predicates; changes query contents, not engine code",
        qualification="Normal gate must select OuterYan; both engines complete five timed runs; use median runtimes",
        correctness="Bare-query multiset ON/OFF and input/outer-predicate equivalence on adversarial tiny fixture",
        performance="CPU9 SF50, 32 threads, 600 seconds per statement per engine; no full correctness timing"
    ), indent=2) + "\n")
    print("Prepared 4 independent pilot queries in " + str(directory), flush=True)


def validate(args):
    binary, database = args.bin.resolve(), args.db.resolve()
    with (args.corpus / "manifest.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    expected = entries()
    assert rows == [r for r, _ in expected], "Pilot manifest differs from generator"
    for row, sql in expected:
        assert (args.corpus / row["path"]).read_text() == sql, row["query_id"]
    counts = query_json(binary, database, "SELECT (SELECT count(*) FROM orders) AS orders, "
                        "(SELECT count(*) FROM customer) AS customer;")
    assert counts == {"orders": 1500000 * args.sf, "customer": 150000 * args.sf}, counts
    order_counts = query_json(binary, database, "SELECT count(*) AS n, count(*) FILTER (WHERE " +
                              rows[0]["selectivity_predicate"] + ") AS matched FROM orders;")
    line_counts = query_json(binary, database, "SELECT count(*) AS n, " + ", ".join(
        "count(*) FILTER (WHERE {}) AS q{}".format(r["lineitem_selectivity_predicate"] or "true", i)
        for i, r in enumerate(rows)) + " FROM lineitem;")
    info = database.stat()
    signature = json.dumps([str(database), info.st_size, info.st_mtime_ns], separators=(",", ":"))
    audit = dict(database=str(database), database_signature=hashlib.sha256(signature.encode()).hexdigest(),
                 binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), scale=args.sf,
                 threads=args.threads, active_benchmark_modified=False, cpu9_performance_claim=False,
                 orders_selectivity_fraction=order_counts["matched"] / order_counts["n"], candidates=[])
    original = (SOURCE_DIR / "tpch" / (QUERY + ".sql")).read_text()
    with tempfile.TemporaryDirectory(prefix="custdist-line-correctness-") as directory:
        fixture = Path(directory) / "tpch_tiny.duckdb"
        extension = binary.parent / "extension/tpch/tpch.duckdb_extension"
        run(binary, fixture, "LOAD '{}'; CALL dbgen(sf=0.001);".format(str(extension).replace("'", "''")))
        run(binary, fixture, "ALTER TABLE orders ALTER COLUMN o_orderdate DROP NOT NULL; "
            "ALTER TABLE lineitem ALTER COLUMN l_shipdate DROP NOT NULL; "
            "INSERT INTO orders SELECT * REPLACE (900001 AS o_orderkey, 900001 AS o_custkey, "
            "DATE '1992-01-03' AS o_orderdate) FROM orders LIMIT 1; "
            "INSERT INTO orders SELECT * REPLACE (900002 AS o_orderkey, NULL AS o_orderdate) FROM orders LIMIT 1; "
            "INSERT INTO lineitem SELECT * REPLACE (900001 AS l_orderkey, DATE '1992-02-01' AS l_shipdate) FROM lineitem LIMIT 1; "
            "INSERT INTO lineitem SELECT * REPLACE (900002 AS l_orderkey, DATE '1992-02-01' AS l_shipdate) FROM lineitem LIMIT 1; "
            "INSERT INTO lineitem SELECT * REPLACE (900003 AS l_orderkey) FROM lineitem LIMIT 1; "
            "INSERT INTO lineitem SELECT * REPLACE (NULL AS l_shipdate) FROM lineitem LIMIT 1; "
            "INSERT INTO lineitem SELECT * REPLACE (DATE '2010-01-01' AS l_shipdate) FROM lineitem LIMIT 1; "
            "INSERT INTO lineitem SELECT * FROM lineitem LIMIT 1;")
        for index, (row, sql) in enumerate(expected):
            off = multiset(binary, fixture, sql, False)
            on = multiset(binary, fixture, sql, True)
            assert off == on, (row["query_id"], "ON/OFF mismatch")
            predicate = row["lineitem_selectivity_predicate"]
            reference = original.rstrip()[:-1] + "\n AND " + predicate + ";" if predicate else original
            assert off == multiset(binary, fixture, reference, False), (row["query_id"], "input predicate rewrite mismatch")
            assert off, "Unexpected empty fixture result"
            decision = explain(binary, database, sql, args.threads)
            fraction = line_counts["q" + str(index)] / line_counts["n"]
            record = dict(query=row["query_id"], variant=row["pilot_variant"],
                          sql_sha256=row["content_sha256"], lineitem_selectivity_fraction=fraction,
                          fixture_rows=sum(off.values()), correctness="bare-query multiset equivalence passed",
                          decision=decision)
            if args.local_timing and decision["selected_plan"] == "OUTERYAN":
                record["local_timing_not_cpu9_evidence"] = local_timing(binary, database, sql, args.threads)
            audit["candidates"].append(record)
            print("{}: selected={}, lineitem={:.4%}, local_speedup={}".format(
                row["pilot_variant"], decision["selected_plan"], fraction,
                record.get("local_timing_not_cpu9_evidence", {}).get("speedup", "not measured")), flush=True)
    args.audit.write_text(json.dumps(audit, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--out", type=Path, help="Generate a new isolated corpus")
    action.add_argument("--corpus", type=Path, help="Validate an existing generated corpus")
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
