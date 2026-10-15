"""Independent mixed-join variants of archived same-grouping queries.

Keep aliases, relations, predicates, projection, tree shape, and the multiset of
join kinds. Reassign join kinds to tree edges. These are new query semantics,
not equivalence-preserving rewrites or certified faster plans.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import balanced_benchmark as b
import benchmark_plan_cohort as cohort
from benchmark_corpus import SQL_TOKEN, count_base_relations


REVISION = "grouping-candidates-20261014"
OUTPUT = b.ROOT / "candidates/grouping_20261014"
JOIN = re.compile(r"\b(INNER|LEFT|RIGHT|FULL)(?:\s+OUTER)?\s+JOIN", re.I)


def masked_structure(sql):
    # All emitted SQL is explicit-join SQL. Ignore only join kind and comments.
    statement = b.body(sql)
    statement = JOIN.sub("JOIN", statement)
    return tuple(t.lower() if not t.startswith(("'", '"')) else t
                 for t in SQL_TOKEN.findall(statement) if not t.startswith(("--", "/*")))


def candidate_definitions(per_query=2):
    if not 1 <= per_query <= 5:
        raise ValueError("Use 1--5 independent variants per source")
    spec = cohort.policy()
    originals = {r["query_id"]: r for r in cohort.archived_rows(spec)}
    identities = {r["sql_fingerprint"] for r in originals.values()}
    candidates, contents, coverage = [], {}, []
    for pin in spec["members"]:
        row = originals[pin["query_id"]]
        if pin["reference_decision_reason"] != "DUCKDB_PLAN" or int(row["relation_count"]) <= 3:
            continue
        source = (cohort.ARCHIVE / row["path"]).read_text()
        body = b.body(source) + "\n"
        kinds = tuple(m.group(1)[0].upper() for m in JOIN.finditer(body))
        if len(kinds) != int(row["relation_count"]) - 1 or len(set(kinds)) < 2:
            raise ValueError("Expected an acyclic, mixed explicit join tree")
        variants = sorted(set(itertools.permutations(kinds)) - {kinds},
                          key=lambda v: hashlib.sha256((row["query_id"] + "".join(v)).encode()).hexdigest())
        accepted = []
        for vector in variants:
            sql = b.legacy.rewrite_join_types(body, vector)
            fingerprint = b.sql_fingerprint(sql, row["family"])
            if fingerprint in identities:
                continue
            if masked_structure(sql) != masked_structure(body):
                raise ValueError("Candidate changed more than join-type assignment")
            if count_base_relations(sql) != int(row["relation_count"]):
                raise ValueError("Candidate changed relation count")
            vector = "".join(vector)
            query = (f"{row['query_class']}__{row['family']}__regroup_20261014__{row['source_seed']}"
                     f"__{row['tree_shape']}__{vector.lower()}__{fingerprint[:12]}__sel_{row['semantic_tier']}")
            if row["aggregate_variant"]:
                query += "__" + row["aggregate_variant"]
            content = (f"-- candidate_revision: {REVISION}; not active benchmark\n"
                       f"-- source_query: {row['query_id']}\n"
                       "-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.\n" + sql)
            new = dict(row, query_id=query, path=f"{row['family']}/{query}.sql",
                       content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                       sql_fingerprint=fingerprint, expression_fingerprint=b.expression_key(sql, row["family"]),
                       join_vector=vector, corpus_revision=REVISION,
                       qualification_status="PENDING_TARGET_PLAN_AND_MEASUREMENT",
                       grouping_source_query=row["query_id"], grouping_source_sha256=row["content_sha256"],
                       grouping_change="permute_join_kinds_on_existing_edges")
            candidates.append(new)
            contents[new["path"]] = content
            identities.add(fingerprint)
            accepted.append(query)
            if len(accepted) == per_query:
                break
        coverage.append(dict(query_id=row["query_id"], family=row["family"],
                             relation_count=row["relation_count"], candidates=len(accepted),
                             candidate_queries=";".join(accepted)))
    return candidates, contents, coverage


def stage(output, per_query=2):
    records, contents, coverage = candidate_definitions(per_query)
    if output.exists():
        if not (output / "manifest.csv").exists():
            raise ValueError("Refusing to overwrite an unmanaged candidate directory")
        prior = b.read_manifest(output / "manifest.csv")
        if {r["path"]: r["content_sha256"] for r in prior} != {
                r["path"]: r["content_sha256"] for r in records}:
            raise ValueError("Existing candidate definitions differ")
        for row in prior:
            if b.digest(output / row["path"]) != row["content_sha256"]:
                raise ValueError("Locally changed candidate")
    for path, content in contents.items():
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    b.write_csv(output / "manifest.csv", records)
    b.write_csv(output / "source_coverage.csv", coverage)
    (output / "queries.txt").write_text("".join(r["path"] + "\n" for r in records))
    b.write_json(output / "proposal.json", dict(
        revision=REVISION, status="INDEPENDENT_CANDIDATES_NOT_ACTIVE",
        source_policy_sha256=b.digest(cohort.POLICY), per_source_limit=per_query,
        counts=dict(Counter(r["family"] for r in records)), source_queries=len(coverage),
        selection="All archived DUCKDB_PLAN queries with at least four relations. "
                  "Deterministic permutations of existing mixed join kinds, deduplicated against all 720 originals. "
                  "No speedup ranking. No changes to relations, equality conditions, predicates, or expression shape.",
        interpretation="New semantics; grouping changes, applicability, selection, correctness and performance "
                       "need target-server verification. Local EXPLAIN is not a CPU9 performance result."))
    print("Independent grouping candidates:", len(records), dict(Counter(r["family"] for r in records)))
    return records


def explain(binary, database, sql):
    env = dict(os.environ)
    env.pop("DUCKDB_OY_FORCE_CANDIDATE", None)
    with tempfile.TemporaryDirectory(prefix="grouping-explain-") as temp:
        trace = Path(temp) / "trace.txt"
        env["DUCKDB_OYTRACE"] = str(trace)
        run = subprocess.run([str(binary), "-readonly", str(database)],
                             input="SET threads=4; SET disabled_optimizers=''; EXPLAIN " + sql,
                             capture_output=True, text=True, env=env, timeout=15)
        if run.returncode:
            raise ValueError(run.stderr.strip()[:500])
        lines = [s for s in trace.read_text().splitlines() if s.startswith("[OY_DECISION]")]
        if not lines:
            raise ValueError("Missing OuterYan decision")
        decision = dict(re.findall(r"(\w+)=([^\s]+)", lines[-1]))
        if decision.get("selection_mode") != "GATED":
            raise ValueError("Expected normal, non-forced optimizer")
        return {k: decision.get(k, "") for k in ("selection_mode", "outer_reordered", "selected_plan", "reason")}


def check_plans(output, binary, databases, report):
    rows = b.read_manifest(output / "manifest.csv")
    records = []
    for i, row in enumerate(rows, 1):
        route = "epinions" if row["family"] == "graph" and row.get("graph_dataset") == "epinions" else row["family"]
        database = databases[route]
        record = dict(query=row["query_id"], family=row["family"], source_query=row["grouping_source_query"],
                      database=str(database), sql_content_sha256=row["content_sha256"], status="NOT_CHECKED")
        try:
            if not database.is_file():
                raise ValueError("Local database unavailable")
            if b.digest(output / row["path"]) != row["content_sha256"]:
                raise ValueError("Candidate SQL changed")
            record.update(explain(binary, database, (output / row["path"]).read_text()), status="EXPLAIN_OK")
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            record.update(status="EXPLAIN_ERROR", detail=str(error))
        records.append(record)
        if i % 25 == 0:
            print(f"Local EXPLAIN {i}/{len(rows)}", flush=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    b.write_csv(report, records)
    print("Local plan-only checks:", dict(Counter((r["status"], r.get("outer_reordered"), r.get("selected_plan")) for r in records)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--per-query", type=int, default=2)
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--duckdb", type=Path, default=b.legacy.REPO_ROOT / "build/release/duckdb")
    parser.add_argument("--report", type=Path, default=b.legacy.SCRIPT_DIR / "results/grouping_candidates_20261014_local.csv")
    for name, default in (("graph", "graph_db"), ("epinions", "graph_epinions.duckdb"),
                          ("tpch", "tpch_1.duckdb"), ("tpcds", "tpcds_1.duckdb"), ("job", "job_db")):
        parser.add_argument("--" + name + "-db", type=Path, default=b.legacy.REPO_ROOT / default)
    args = parser.parse_args()
    stage(args.output, args.per_query)
    if args.explain:
        check_plans(args.output, args.duckdb, {f: getattr(args, f + "_db") for f in ("graph", "epinions", "tpch", "tpcds", "job")}, args.report)
