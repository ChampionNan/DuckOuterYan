#!/usr/bin/env python3
"""Validate the isolated custdist candidates without modifying the active corpus."""

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile

from prepare_slow_five_retest import environment, explain, local_timing, query_json


def run(binary, database, sql, output="csv"):
    result = subprocess.run(
        [str(binary), "-no-init", "-bail", str(database), "-" + output, "-noheader"],
        input=sql, text=True, capture_output=True, timeout=120, env=environment())
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout


def multiset(binary, database, sql, enabled):
    settings = "SET threads=2; SET max_execution_time=60000; SET disabled_optimizers='{}';\n".format(
        "" if enabled else "outer_yan")
    return Counter(tuple(row) for row in csv.reader(io.StringIO(run(binary, database, settings + sql))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--bin", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--sf", type=int, required=True)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--local-timing", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    binary, database = args.bin.resolve(), args.db.resolve()
    rows = list(csv.DictReader((args.corpus / "manifest.csv").open()))
    assert len(rows) == 6
    counts = query_json(binary, database, "SELECT count(*) AS n FROM orders;")
    assert counts["n"] == 1500000 * args.sf
    sqls = {}
    for row in rows:
        sql = (args.corpus / row["path"]).read_text()
        assert hashlib.sha256(sql.encode()).hexdigest() == row["content_sha256"]
        sqls[(row["pilot_days"], row["pilot_placement"])] = sql
    predicates = [row["selectivity_predicate"] for row in rows]
    calibration = query_json(binary, database, "SELECT count(*) AS n, " + ", ".join(
        "count(*) FILTER (WHERE {}) AS q{}".format(p, i) for i, p in enumerate(predicates)) + " FROM orders;")
    info = database.stat()
    signature = json.dumps([str(database), info.st_size, info.st_mtime_ns], separators=(",", ":"))
    audit = dict(database=str(database), database_signature=hashlib.sha256(signature.encode()).hexdigest(),
                 scale=args.sf, threads=args.threads,
                 binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                 active_benchmark_modified=False, cpu9_performance_claim=False, candidates=[])
    with tempfile.TemporaryDirectory(prefix="custdist-correctness-") as directory:
        fixture = Path(directory) / "tpch_tiny.duckdb"
        extension = binary.parent / "extension/tpch/tpch.duckdb_extension"
        run(binary, fixture, "LOAD '{}'; CALL dbgen(sf=0.001);".format(str(extension).replace("'", "''")))
        # Extra null/unmatched order rows exercise the retained outer WHERE.
        run(binary, fixture, "ALTER TABLE orders ALTER COLUMN o_orderdate DROP NOT NULL; "
            "INSERT INTO orders SELECT * REPLACE (900001 AS o_orderkey, 900001 AS o_custkey, "
            "DATE '1992-01-03' AS o_orderdate) FROM orders LIMIT 1; "
            "INSERT INTO orders SELECT * REPLACE (900002 AS o_orderkey, 900002 AS o_custkey, "
            "NULL AS o_orderdate) FROM orders LIMIT 1; "
            "INSERT INTO lineitem SELECT * REPLACE (900001 AS l_orderkey) FROM lineitem LIMIT 1; "
            "INSERT INTO lineitem SELECT * REPLACE (900002 AS l_orderkey) FROM lineitem LIMIT 1; "
            "INSERT INTO lineitem SELECT * REPLACE (900003 AS l_orderkey) FROM lineitem LIMIT 1;")
        reference = {}
        for index, row in enumerate(rows):
            key = row["pilot_days"], row["pilot_placement"]
            sql = sqls[key]
            off = multiset(binary, fixture, sql, False)
            on = multiset(binary, fixture, sql, True)
            assert off == on, (key, "ON/OFF mismatch")
            if row["pilot_placement"] == "where":
                reference[row["pilot_days"]] = off
            else:
                assert off == reference[row["pilot_days"]], (key, "input rewrite mismatch")
            fraction = calibration["q" + str(index)] / calibration["n"]
            assert 0.05 <= fraction < 0.4, fraction
            decision = explain(binary, database, sql, args.threads)
            record = dict(query=row["query_id"], days=int(row["pilot_days"]),
                          placement=row["pilot_placement"], selectivity_fraction=fraction,
                          correctness="bare-query multiset equivalent on tiny fixture",
                          fixture_rows=sum(off.values()), decision=decision)
            if args.local_timing:
                record["local_timing_not_cpu9_evidence"] = local_timing(binary, database, sql, args.threads)
            audit["candidates"].append(record)
            print("{}: selected={}, selectivity={:.4%}, local_speedup={}".format(
                row["query_id"], decision["selected_plan"], fraction,
                record.get("local_timing_not_cpu9_evidence", {}).get("speedup", "not measured")), flush=True)
    args.out.write_text(json.dumps(audit, indent=2) + "\n")


if __name__ == "__main__":
    main()
