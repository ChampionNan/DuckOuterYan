#!/usr/bin/env python3
"""Prepare isolated G-H-LD-05 predicate-placement/selectivity experiments.

The active benchmark and optimizer remain untouched. Input-filter variants
retain the outer WHERE: rows whose order date does not qualify cannot survive
that WHERE, even if removing them creates additional null-extended rows.
"""

import argparse
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

from benchmark_corpus import count_base_relations, sql_fingerprint

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "auto_test/outerjoin_benchmark/benchmark"
QUERY = "graph__tpch__th_real_custdist__left_deep__lrf__65a983cc__sel_medium"
SOURCE_SHA = "e858780681373c09c96763d991d488c822a86646776f28da504f99520532075d"
REVISION = "custdist-predicate-pilot-20261015"


def prepare():
    with (ACTIVE / "manifest.csv").open(newline="") as handle:
        source = next(row for row in csv.DictReader(handle) if row["query_id"] == QUERY)
    sql = (ACTIVE / source["path"]).read_text()
    assert hashlib.sha256(sql.encode()).hexdigest() == SOURCE_SHA
    old = source["selectivity_predicate"]
    assert sql.count(old) == 1
    assert sql.count("LEFT OUTER JOIN orders   ON") == 1
    result = []
    for days in (840, 366, 180):
        first = date(1992, 1, 1)
        last = first + timedelta(days=days - 1)
        predicate = "orders.o_orderdate BETWEEN DATE '{}' AND DATE '{}'".format(first, last)
        assert days != 840 or predicate == old
        for placement in ("where", "input"):
            content = sql.replace(old, predicate, 1)
            if placement == "input":
                scan = "(SELECT * FROM orders WHERE {}) AS orders".format(
                    predicate.replace("orders.", ""))
                content = content.replace("LEFT OUTER JOIN orders   ON",
                                          "LEFT OUTER JOIN " + scan + " ON", 1)
                assert content.count("WHERE " + predicate) == 1
            assert count_base_relations(content) == 4
            identifier = QUERY + "__custdist_20261015_{}_d{}".format(placement, days)
            row = dict(source, query_id=identifier, path="tpch/" + identifier + ".sql",
                       corpus_revision=REVISION,
                       content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                       sql_fingerprint=sql_fingerprint(content, "tpch"),
                       selectivity_predicate=predicate,
                       input_filter_placement="orders input plus unchanged outer WHERE"
                       if placement == "input" else "outer WHERE",
                       pilot_source_query=QUERY, pilot_source_sha256=SOURCE_SHA,
                       pilot_short_id="G-H-LD-05", pilot_days=str(days),
                       pilot_placement=placement,
                       pilot_role="original_control" if days == 840 and placement == "where" else "candidate",
                       equivalent_to_active="true" if days == 840 else "false",
                       qualification_status="PENDING_CPU9_MEASUREMENT",
                       qualification_min_speedup="0.75",
                       parameter_policy="Isolated query pilot; no cost-model changes or automatic promotion")
            if days != 840:
                for key in ("target_fraction", "calibration_rows", "calibration_qualified_rows",
                            "calibration_fraction", "calibration_in_range"):
                    row[key] = ""
            result.append((row, content))
    assert len({r["sql_fingerprint"] for r, _ in result}) == len(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    entries = prepare()
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "tpch").mkdir()
    for row, sql in entries:
        (args.out / row["path"]).write_text(sql)
    with (args.out / "manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(entries[0][0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(row for row, _ in entries)
    (args.out / "queries.txt").write_text("".join(row["path"] + "\n" for row, _ in entries))
    (args.out / "timing_queries.txt").write_text("".join(
        row["path"] + "\n" for row, _ in entries
        if row["pilot_placement"] == "input" or row["pilot_role"] == "original_control"))
    (args.out / "protocol.json").write_text(json.dumps(dict(
        revision=REVISION, source_query=QUERY, source_sha256=SOURCE_SHA,
        source_selectivity_fraction=0.3490114, active_benchmark_modified=False,
        optimizer_modified=False, target_speedup=0.75,
        validation="Compare bare-query result multisets on a small fixture; CPU9 SF50 normal-gate plan and five-run median required.",
        equivalent_rewrite="Input date predicate is duplicated, not moved: the original null-rejecting outer WHERE is retained.",
        candidates=[dict(query=r["query_id"], days=int(r["pilot_days"]),
                         placement=r["pilot_placement"], equivalent_to_active=r["equivalent_to_active"])
                    for r, _ in entries]), indent=2) + "\n")
    print("Prepared {} isolated queries in {}".format(len(entries), args.out))


if __name__ == "__main__":
    main()
