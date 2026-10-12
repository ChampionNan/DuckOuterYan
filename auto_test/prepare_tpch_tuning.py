#!/usr/bin/env python3
"""Stage TPC-H-only SQL replacements for review and a fresh CPU9 pilot.

This does not change the active corpus, the optimizer, or measured results.
Promotion requires fresh measurements: 80 selected TPC-H queries is a target,
not something a query generator can certify.
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import balanced_benchmark as b
from benchmark_corpus import count_base_relations

POLICY = b.ROOT / "sources/tpch_query_tuning_20261012.json"
ACTIVE = b.ROOT / "benchmark"
OUTPUT = b.ROOT / "candidates/tpch_query_tuning_20261012"
JOIN = re.compile(r"\b(INNER|LEFT|RIGHT|FULL)(?:\s+OUTER)?\s+JOIN", re.I)
END_DATES = {
    "tpch_q03_order_revenue": "1994-10-06",
    "tpch_q05_region_sales": "1995-08-01",
    "tpch_q07_trade_flow": "1996-12-31",
    "tpch_q08_market_share": "1996-12-31",
    "sqlstorm_tpch_17751": "1997-12-31",
    "sqlstorm_tpch_25509": "1996-12-31",
    "th_real_custdist": "1997-01-03",
}
DONORS = {
    "q5_bushy_donor": "db73eb5f",
    "q8_right_donor": "92643cc5",
    "storm17751_bushy_donor": "5b0bbaf5",
}


def sha(content):
    return hashlib.sha256(content.encode()).hexdigest()


def from_expression(sql):
    return re.split(r"\bWHERE\b", re.split(r"\bFROM\b", b.body(sql), maxsplit=1)[1], maxsplit=1)[0].strip()


def equalities(sql):
    return {tuple(sorted(match.groups())) for match in b.legacy.SIMPLE_EDGE_EQUALITY.finditer(sql)}


def replacement_sql(pin, records):
    old = next(r for r in records if r["query_id"] == pin["original"]["query_id"])
    sql = b.body((ACTIVE / old["path"]).read_text())
    expr = from_expression(sql)
    rule = pin["rule"]
    if rule in DONORS:
        donor = next(r for r in records if r["expression_fingerprint"].startswith(DONORS[rule]))
        if (donor["family"], donor["source_seed"], donor["tree_shape"]) != (
                "tpch", old["source_seed"], old["tree_shape"]):
            raise ValueError("Pattern donor changed source or tree shape")
        expr = from_expression((ACTIVE / donor["path"]).read_text())
    elif rule == "q3_full_right":
        expr, n = re.subn(r"\bLEFT OUTER JOIN\b", "RIGHT OUTER JOIN", expr)
        if n != 1:
            raise ValueError("Unexpected Q3 pattern")
    elif rule == "q5_alternate_right":
        seed = next(s for s in b.legacy.SEEDS if s.seed_id == old["source_seed"])
        expr = b.expression(seed, old["tree_shape"], tuple("FLIR"), traversal=1)
    elif rule == "custdist_r_l_f":
        kinds = iter(("RIGHT OUTER JOIN", "LEFT OUTER JOIN", "FULL OUTER JOIN"))
        expr, n = JOIN.subn(lambda _: next(kinds), expr)
        if n != 3:
            raise ValueError("Unexpected customer-distribution control")
    elif rule != "selectivity_only":
        raise ValueError("Unknown TPC-H tuning rule")
    if equalities(expr) != equalities(from_expression(sql)):
        raise ValueError("TPC-H tuning must retain every source equality edge")
    sql = sql.replace(from_expression(sql), expr, 1)
    days = {"low": 48, "medium": 240, "high": pin["high_days"]}[old["semantic_tier"]]
    end = dt.date.fromisoformat(END_DATES[old["source_seed"]])
    start = end - dt.timedelta(days=days-1)
    anchor = old["selectivity_anchor"]
    predicate = f"{anchor} BETWEEN DATE '{start}' AND DATE '{end}'"
    sql = b.legacy.replace_where(sql, predicate).strip() + "\n"
    if count_base_relations(sql) != int(old["relation_count"]):
        raise ValueError("TPC-H tuning changed the relation count")
    if len(set(JOIN.findall(sql))) < 2:
        raise ValueError("TPC-H candidate must retain mixed joins")
    return sql, predicate


def calibrated_count(binary, database, row, predicate):
    alias = row["selectivity_denominator"].split()[-1]
    predicate = predicate.replace(row["selectivity_anchor"], alias + "." + row["selectivity_anchor"].split(".")[-1])
    query = (f"SELECT count(*) AS n, count(*) FILTER (WHERE {predicate}) AS qualified "
             f"FROM {row['selectivity_denominator']};")
    proc = subprocess.run([str(binary), "-readonly", str(database), "-json", "-c", query],
                          check=True, text=True, capture_output=True, timeout=30)
    result = json.loads(proc.stdout)[0]
    fraction = result["qualified"] / result["n"]
    lower, upper = float(row["target_min_fraction"]), float(row["target_max_fraction"])
    lower_ok = fraction >= lower if row["target_min_inclusive"] == "true" else fraction > lower
    upper_ok = fraction <= upper if row["target_max_inclusive"] == "true" else fraction < upper
    if not lower_ok or not upper_ok or fraction > float(row["calibration_fraction"]):
        raise ValueError(f"Candidate must reduce selectivity inside the same band: {row['query_id']}")
    return result, fraction


def plan_decision(binary, database, sql, threads):
    with tempfile.TemporaryDirectory(prefix="tpch-tuning-explain-") as work:
        trace = Path(work) / "trace"
        subprocess.run([str(binary), "-readonly", str(database)], check=True, text=True,
                       input=f"SET threads={threads}; SET disabled_optimizers=''; EXPLAIN (FORMAT JSON) {sql}",
                       capture_output=True, timeout=30, env=dict(os.environ, DUCKDB_OYTRACE=str(trace)))
        lines = [line for line in trace.read_text().splitlines() if line.startswith("[OY_DECISION]")]
        if not lines:
            raise ValueError("EXPLAIN did not emit an OuterYan decision")
        return dict(re.findall(r"(\w+)=([^\s]+)", lines[-1]))


def stage(binary, database, output, explain=False, threads=4):
    spec = json.loads(POLICY.read_text())
    records = b.read_manifest(ACTIVE / "manifest.csv")
    if b.digest(ACTIVE / "manifest.csv") != spec["active_manifest_sha256"]:
        raise ValueError("Active manifest changed; review/rebase this pinned proposal first")
    if dict(Counter(r["family"] for r in records)) != spec["expected_counts"]:
        raise ValueError("Active family counts changed")
    if len(spec["reference_selected_queries"]) != 281:
        raise ValueError("Reference measured cohort must have 281 distinct slots")
    selected = {r["query_id"] for r in records if r["query_id"] in spec["reference_selected_queries"]}
    if len(selected) != 281 or sum(r["family"] == "tpch" for r in records if r["query_id"] in selected) != 80:
        raise ValueError("Reference selected TPC-H cohort changed")
    candidates, mapping, contents, decisions = [], [], {}, []
    identities = {r["sql_fingerprint"] for r in records}
    for pin in spec["replacements"]:
        old = next(r for r in records if r["query_id"] == pin["original"]["query_id"])
        if (any(old[k] != v for k, v in pin["original"].items())
                or old["family"] != "tpch" or old["query_id"] not in selected):
            raise ValueError("TPC-H replacement metadata changed")
        if b.digest(ACTIVE / old["path"]) != old["content_sha256"]:
            raise ValueError("TPC-H replacement SQL changed")
        sql, predicate = replacement_sql(pin, records)
        count, fraction = calibrated_count(binary, database, old, predicate)
        expression_key = b.expression_key(sql, "tpch")
        vector = "".join(kind[0].upper() for kind in JOIN.findall(sql))
        slot = pin["short_query"].lower().replace("-", "_")
        query = (f"{old['query_class']}__tpch__tuning_20261012_{slot}__{old['source_seed']}"
                 f"__{old['tree_shape']}__{vector.lower()}__{expression_key[:8]}__sel_{old['semantic_tier']}")
        if old["aggregate_variant"]:
            query += "__" + old["aggregate_variant"]
        content = (f"-- query_tuning: {spec['revision']}; replaces {old['query_id']}\n"
                   f"-- source: {old['source_benchmark']} {old['source_query']}\n"
                   "-- performance-conditioned candidate; fresh CPU9 measurement required\n" + sql)
        fingerprint = b.sql_fingerprint(content, "tpch")
        if fingerprint in identities:
            raise ValueError(f"Candidate duplicates an active or proposed SQL: {query}")
        identities.add(fingerprint)
        row = dict(old, query_id=query, path=f"tpch/{query}.sql", content_sha256=sha(content),
                   sql_fingerprint=fingerprint, expression_fingerprint=expression_key,
                   join_vector=vector,
                   selectivity_predicate=predicate, filter_design_revision=spec["revision"],
                   selectivity_profile=spec["revision"] + "/" + old["selectivity_profile"],
                   selectivity_denominator=old["selectivity_denominator"].split()[0] + " " + old["selectivity_anchor"].split(".")[0],
                   target_fraction={"low": .02, "medium": .10, "high": .44 if pin["high_days"] == 1056 else .42}[old["semantic_tier"]],
                   calibration_rows=count["n"], calibration_qualified_rows=count["qualified"],
                   calibration_fraction=fraction, calibration_in_range="true",
                   parameter_policy=spec["selection_policy"],
                   qualification_status="PENDING_CPU9_MEASUREMENT", tpch_tuning_revision=spec["revision"],
                   tuning_replaces_query_id=old["query_id"], tuning_replaces_sha256=old["content_sha256"])
        candidates.append(row)
        contents[row["path"]] = content
        mapping.append(dict(short_query=pin["short_query"], original_query=old["query_id"],
                            proposed_query=query, change=pin["rule"], tier=old["semantic_tier"],
                            old_fraction=old["calibration_fraction"], new_fraction=fraction,
                            old_join_vector=old["join_vector"], new_join_vector=row["join_vector"],
                            old_speedup_reference_only=pin["historical_speedup"],
                            new_speedup="PENDING", new_selected="PENDING_CPU9", new_predicate=predicate))
        if explain:
            decision = plan_decision(binary, database, sql, threads)
            decisions.append(dict(query=query, **decision))
            print(f"{pin['short_query']}: {fraction:.4%} {row['join_vector']} "
                  f"local selection={decision.get('selected_plan')} (not a timing result)", flush=True)
    replacements = {r["tuning_replaces_query_id"]: r for r in candidates}
    proposal = [replacements.get(r["query_id"], r) for r in records]
    for columns in (("family",), ("family", "tree_shape"), ("family", "query_class"),
                    ("family", "semantic_tier"), ("family", "relation_count")):
        if Counter(tuple(str(r[k]) for k in columns) for r in proposal) != Counter(tuple(str(r[k]) for k in columns) for r in records):
            raise ValueError(f"Proposal changed the quota {columns}")
    if output.exists():
        raise ValueError("Output already exists; choose a new --out to avoid overwriting a reviewed proposal")
    output.mkdir(parents=True)
    for name, content in contents.items():
        target = output / name
        target.parent.mkdir(exist_ok=True)
        target.write_text(content)
    b.write_csv(output / "manifest.csv", candidates)
    b.write_csv(output / "replacement_map.csv", mapping)
    b.write_csv(output / "proposed_full_manifest.csv", proposal)
    b.write_csv(output / "local_explain_decisions.csv", decisions)
    (output / "queries.txt").write_text("".join(r["path"] + "\n" for r in candidates))
    (output / "baseline_queries.txt").write_text("".join(
        next(r["path"] for r in records if r["query_id"] == pin["original"]["query_id"]) + "\n"
        for pin in spec["replacements"]))
    b.write_json(output / "proposal.json", dict(revision=spec["revision"], policy_sha256=b.digest(POLICY),
                 active_manifest_sha256=spec["active_manifest_sha256"], candidate_count=len(candidates),
                 proposed_counts=spec["expected_counts"], active_corpus_modified=False,
                 selected_total_target=281, selected_tpch_target=80, local_database=str(database),
                 local_binary_sha256=b.digest(binary), status="PENDING_CPU9_MEASUREMENT",
                 note="Not promoted. Unchanged slots retain SQL only; candidates inherit no timing or correctness evidence."))
    print(f"Staged {len(candidates)} TPC-H candidates at {output}; active 720-query corpus unchanged.")
    return candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin", type=Path, default=b.legacy.REPO_ROOT / "build/release/duckdb")
    parser.add_argument("--db", type=Path, required=True, help="Read-only local calibration database")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    stage(args.bin.resolve(), args.db.resolve(), args.out.resolve(), args.explain, args.threads)


if __name__ == "__main__":
    main()
