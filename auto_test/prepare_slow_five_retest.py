#!/usr/bin/env python3
"""Stage selectivity-only candidates for the five remaining sub-0.7 queries.

No active SQL or result is replaced. All candidates retain the source's
selectivity band, relations, join expression, projection and aggregation.
"""
import argparse
import csv
from datetime import date, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import tempfile

from benchmark_corpus import sql_fingerprint

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "auto_test/outerjoin_benchmark/benchmark"
REVISION = "slow-five-selectivity-20261014"
SPECS = (
    ("G-H-LD-03", "graph__tpch__th_real_custdist__left_deep__lrf__65a983cc__sel_medium",
     "0c14c5c3d847a2a7ff6583da4e7bac34ae3d3f708a18afd0e035e97b6e7d684a"),
    ("G-H-LD-05", "graph__tpch__th_real_custdist__left_deep__lrf__65a983cc__sel_high",
     "98c18ce6d4ac1f86653abfc224ea7ed4ca1f5128c2df84df588459150589c235"),
    ("A-H-B-07", "aggregate__tpch__tuning_20261012_a_h_b_07__sqlstorm_tpch_25509__bushy__lfilr__92747bc0__sel_high__grouped_count",
     "4fc59a70f9c04bb95fd2fd6546b7dd68d97c84635fa048222007f35d46994761"),
    ("A-J-RD-05", "aggregate__job__job_10a_cast_credits__right_deep__rlif__87f83502__sel_medium__grouped_count",
     "50a5191307d0af3414203b6febfd5e60a62ea198a948e1e73762d5a6e8d69c29"),
    ("A-J-B-07", "aggregate__job__sqlstorm_job_11914__bushy__ilrff__9a0ef4e8__sel_high__grouped_count",
     "fdc5e84e3ff9e082bbd32a8b65362b848c02173e0283547bec3dc4994e52288a"),
)
WINDOWS = {
    "G-H-LD-03": ((930, "early"), (840, "early"), (950, "early")),
    "G-H-LD-05": ((1000, "early"), (1200, "early"), (1440, "early")),
    "A-H-B-07": ((970, "late"), (1200, "late"), (1320, "late")),
}
YEARS = {
    "A-J-RD-05": ((2007, None), (2006, 2012), (2005, 2011)),
    "A-J-B-07": ((2005, None), (2004, 2012), (2003, 2011)),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment():
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("DUCKDB_OY", "DUCKDB_SJ_"))}


def variants(short, anchor):
    if short in YEARS:
        return [("y" + str(lo) + ("_" + str(hi) if hi else ""),
                 "{} BETWEEN {} AND {}".format(anchor, lo, hi) if hi else anchor + " >= " + str(lo))
                for lo, hi in YEARS[short]]
    result = []
    for days, location in WINDOWS[short]:
        start, end = date(1992, 1, 1), date(1998, 8, 2)
        if location == "early":
            end = start + timedelta(days=days - 1)
        else:
            start = end - timedelta(days=days - 1)
        result.append(("d{}_{}".format(days, location),
                       "{} BETWEEN DATE '{}' AND DATE '{}'".format(anchor, start, end)))
    return result


def assemble(active=ACTIVE):
    with (active / "manifest.csv").open(newline="") as handle:
        records = {r["query_id"]: r for r in csv.DictReader(handle)}
    entries, fingerprints = [], set()
    for short, query, expected_hash in SPECS:
        original = records[query]
        source = active / original["path"]
        if digest(source) != expected_hash or original["content_sha256"] != expected_hash:
            raise ValueError("Frozen source SQL changed: " + short)
        sql, old_predicate = source.read_text(), original["selectivity_predicate"]
        if sql.count(old_predicate) != 1:
            raise ValueError("Expected a single source predicate: " + short)
        for tag, predicate in [("original", old_predicate)] + variants(short, original["selectivity_anchor"]):
            content = sql.replace(old_predicate, predicate, 1)
            if content.replace(predicate, old_predicate, 1) != sql:
                raise ValueError("Only the predicate may change")
            fingerprint = sql_fingerprint(content, original["family"])
            if fingerprint in fingerprints:
                raise ValueError("Duplicate pilot SQL")
            fingerprints.add(fingerprint)
            candidate = tag != "original"
            identifier = query + "__slow5_20261014_" + tag
            row = dict(original, query_id=identifier, path=original["family"] + "/" + identifier + ".sql",
                       content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                       sql_fingerprint=fingerprint, selectivity_predicate=predicate,
                       corpus_revision=REVISION, pilot_source_query=query, pilot_source_sha256=expected_hash,
                       pilot_short_id=short, pilot_variant=tag,
                       pilot_role="candidate" if candidate else "original_control",
                       qualification_status="PENDING_CPU9_MEASUREMENT", qualification_min_speedup="0.7",
                       qualification_min_runtime_s="0",
                       parameter_policy="Selectivity-only pilot within the original band; no automatic promotion")
            for key in ("target_fraction", "calibration_rows", "calibration_qualified_rows",
                        "calibration_fraction", "calibration_in_range"):
                row[key] = ""
            entries.append((row, content))
    return entries


def query_json(binary, database, query):
    result = subprocess.run([str(binary), "-no-init", "-bail", "-readonly", str(database), "-json"],
                            input="SET disabled_optimizers='outer_yan'; SET max_execution_time=600000; " + query,
                            text=True, capture_output=True, timeout=630, env=environment(), check=True)
    return json.loads(result.stdout)[0]


def calibrate(binary, databases, entries, expected_sf):
    counts = query_json(binary, databases["tpch"], "SELECT (SELECT count(*) FROM orders) AS orders, "
                        "(SELECT count(*) FROM customer) AS customer;")
    if counts != {"orders": 1500000 * expected_sf, "customer": 150000 * expected_sf}:
        raise ValueError("TPC-H scale mismatch: " + repr(counts))
    for family in ("tpch", "job"):
        rows = [r for r, _ in entries if r["family"] == family]
        table, column = ("orders", "o_orderdate") if family == "tpch" else ("title", "production_year")
        predicates = [r["selectivity_predicate"].replace(r["selectivity_anchor"], column) for r in rows]
        fields = ["count(*) AS n"] + ["count(*) FILTER (WHERE {}) AS q{}".format(p, i) for i, p in enumerate(predicates)]
        totals = query_json(binary, databases[family], "SELECT " + ", ".join(fields) + " FROM " + table)
        for i, row in enumerate(rows):
            fraction = totals["q" + str(i)] / totals["n"]
            lo, hi = float(row["target_min_fraction"]), float(row["target_max_fraction"])
            valid = (fraction >= lo if row["target_min_inclusive"] == "true" else fraction > lo)
            valid &= fraction <= hi if row["target_max_inclusive"] == "true" else fraction < hi
            if not valid:
                raise ValueError("Selectivity left the source band: " + row["query_id"])
            row.update(target_fraction=str(fraction), calibration_fraction=str(fraction),
                       calibration_rows=str(totals["n"]), calibration_qualified_rows=str(totals["q" + str(i)]),
                       calibration_in_range="true")
    return counts


def explain(binary, database, sql, threads):
    with tempfile.TemporaryDirectory(prefix="slow-five-explain-") as temporary:
        trace = Path(temporary) / "decision.trace"
        env = environment()
        env["DUCKDB_OYTRACE"] = str(trace)
        subprocess.run([str(binary), "-no-init", "-bail", "-readonly", str(database)],
                       input="SET threads={}; SET disabled_optimizers=''; EXPLAIN (FORMAT JSON) ".format(threads) + sql,
                       text=True, capture_output=True, timeout=60, env=env, check=True)
        lines = [line for line in trace.read_text().splitlines() if line.startswith("[OY_DECISION]")]
        if not lines:
            raise ValueError("Missing OuterYan decision")
        return dict(re.findall(r"(\w+)=([^\s]+)", lines[-1]))


def local_timing(binary, database, sql, threads):
    """Directional local diagnostics only, never a replacement CPU9 result."""
    times = {}
    for mode, disabled in (("duckdb", "outer_yan"), ("outeryan", "")):
        commands = (".mode trash\n.timer off\nSET threads={}; SET disabled_optimizers='{}'; "
                    "SET max_execution_time=600000;\n{}\n.timer on\n{}\n.timer off\n").format(
                        threads, disabled, sql, "\n".join([sql] * 3))
        result = subprocess.run([str(binary), "-no-init", "-bail", "-readonly", str(database)],
                                input=commands, text=True, capture_output=True, timeout=2500,
                                env=environment(), check=True)
        samples = [float(v) for v in re.findall(r"Run Time.*?real\s+([\d.]+)", result.stdout)]
        if len(samples) != 3:
            raise ValueError("Missing local timing samples: " + result.stdout)
        times[mode + "_samples"] = samples
        times[mode + "_s"] = statistics.median(samples)
    times["speedup"] = times["duckdb_s"] / times["outeryan_s"]
    return times


def bare_equivalence(binary, database, sql, threads):
    """Compare complete local result multisets without changing the bare query."""
    results = []
    for disabled in ("outer_yan", ""):
        result = subprocess.run([str(binary), "-no-init", "-bail", "-readonly", str(database), "-csv", "-noheader"],
                                input="SET threads={}; SET disabled_optimizers='{}'; "
                                      "SET max_execution_time=600000; ".format(threads, disabled) + sql,
                                text=True, capture_output=True, timeout=630, env=environment(), check=True)
        results.append(sorted(tuple(row) for row in csv.reader(io.StringIO(result.stdout))))
    if results[0] != results[1]:
        raise ValueError("Local bare-query result mismatch")
    return len(results[0])


def materialize(output, entries, audit):
    output.mkdir(parents=True, exist_ok=False)
    for row, sql in entries:
        path = output / row["path"]
        path.parent.mkdir(exist_ok=True)
        path.write_text(sql)
    fields = list(dict.fromkeys(k for row, _ in entries for k in row))
    with (output / "manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(row for row, _ in entries)
    (output / "queries.txt").write_text("".join(row["path"] + "\n" for row, _ in entries))
    (output / "pilot_provenance.json").write_text(json.dumps(audit, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bin", type=Path, required=True)
    parser.add_argument("--tpch-db", type=Path, required=True)
    parser.add_argument("--job-db", type=Path, required=True)
    parser.add_argument("--tpch-sf", type=int, default=50)
    parser.add_argument("--threads", type=int, default=32)
    parser.add_argument("--local-timing", action="store_true")
    parser.add_argument("--correctness-tpch-db", type=Path,
                        help="Optional small TPC-H fixture: check all bare queries, using JOB's existing DB")
    args = parser.parse_args()
    if args.out.exists() or args.threads < 1:
        parser.error("A fresh output directory and positive thread count are required")
    binary = args.bin.resolve()
    databases = {"tpch": args.tpch_db.resolve(), "job": args.job_db.resolve()}
    if not binary.is_file() or not all(p.is_file() for p in databases.values()):
        parser.error("Existing binary and databases required")
    if args.correctness_tpch_db and not args.correctness_tpch_db.is_file():
        parser.error("Existing small correctness database required")
    entries = assemble()
    counts = calibrate(binary, databases, entries, args.tpch_sf)
    audit = dict(revision=REVISION, active_manifest_sha256=digest(ACTIVE / "manifest.csv"),
                 active_benchmark_modified=False, optimizer_modified=False, target_speedup=.7,
                 binary_sha256=digest(binary), tpch_scale=args.tpch_sf, tpch_counts=counts,
                 threads=args.threads, query_count=len(entries), controls=5, candidates=15,
                 acceptance="Fresh CPU9 measurement, both engines finish, OuterYan selected, ratio >= 0.7. No fallback imputation.",
                 decisions=[])
    for row, sql in entries:
        decision = explain(binary, databases[row["family"]], sql, args.threads)
        record = dict(query_id=row["query_id"], short_query=row["pilot_short_id"],
                      variant=row["pilot_variant"], fraction=float(row["calibration_fraction"]), decision=decision)
        if args.local_timing:
            record["local_timing_not_cpu9_evidence"] = local_timing(binary, databases[row["family"]], sql, args.threads)
        if args.correctness_tpch_db:
            check_db = args.correctness_tpch_db.resolve() if row["family"] == "tpch" else databases["job"]
            record["local_correctness"] = dict(database=str(check_db), status="equivalent",
                rows=bare_equivalence(binary, check_db, sql, args.threads),
                sql_wrapped=False, cpu9_correctness_claim=False)
        audit["decisions"].append(record)
        print("{} {}: fraction={:.2%}; selected={}; local_ratio={}; correctness={}".format(
            row["pilot_short_id"], row["pilot_variant"], record["fraction"], decision["selected_plan"],
            record.get("local_timing_not_cpu9_evidence", {}).get("speedup", "not measured"),
            record.get("local_correctness", {}).get("status", "not checked")), flush=True)
    materialize(args.out.resolve(), entries, audit)
    print("Prepared five controls and fifteen selectivity-only candidates at " + str(args.out.resolve()))


if __name__ == "__main__":
    main()
