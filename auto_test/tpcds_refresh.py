"""Pinned TPC-DS recovery component; generation never reads experiment results.

This is explicitly performance-conditioned research curation. Historical timings
explain template selection; they never certify newly generated candidates.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil

import balanced_benchmark as b

POLICY = b.ROOT / "sources/tpcds_refresh_20261005.json"
ROLE = "historical_selectivity_recovery"
MARKER = "tpcds_refresh.json"


def policy():
    return json.loads(POLICY.read_text(encoding="utf-8"))


def is_recovery(row):
    return row.get("evaluation_role") == ROLE


def recovery_queries(spec=None, *, role=ROLE, namespace="recovery", component="historical_recovery",
                     revision_key="tpcds_refresh_revision", template_key="recovery_template", parameter_policy=None):
    """Keep archived FROM expressions and filter relations in three cohorts."""
    spec = policy() if spec is None else spec
    design = b.load_design()
    for template in spec["templates"]:
        source = b.ROOT / template["archive_sql"]
        if b.digest(source) != template["archive_sha256"]:
            raise ValueError(f"Historical recovery source changed: {source}")
        original = b.body(source.read_text(encoding="utf-8"))
        if b.expression_key(original, "tpcds") != template["expression_fingerprint"]:
            raise ValueError(f"Historical join expression changed: {source}")
        aggregate = template["aggregate_variant"]
        if aggregate:
            if aggregate != "global_count" or re.search(r"\bGROUP\s+BY\b", original, re.I):
                raise ValueError(f"Unsupported historical aggregation: {source}")
            original, count = b.legacy.SELECT_LIST_PATTERN.subn(
                "SELECT COUNT(*) AS row_count\nFROM ", original, count=1)
            if count != 1:
                raise ValueError(f"Unexpected SELECT list: {source}")
        control = template["source_benchmark"] == "Industry-inspired synthetic control"
        category = "aggregate" if aggregate else "graph" if control else "join"
        for tier in b.TIERS:
            metadata = b.profile_metadata(design, template["selectivity_profile"],
                                          template["selectivity_anchor"], tier)
            metadata["filter_design_revision"] = spec["revision"]
            metadata["parameter_policy"] = parameter_policy or (
                "Historical-performance-selected pattern; fixed 3/30/55 identifier buckets on the old filter relation"
                if template["selectivity_profile"].startswith("recovery_modulo_") else
                "Historical-performance-selected pattern; frozen semantic cohorts") + "; CPU9 audit required"
            sql = b.legacy.replace_where(original, metadata["selectivity_predicate"]).strip() + "\n"
            if b.expression_key(sql, "tpcds") != template["expression_fingerprint"]:
                raise ValueError(f"Recovery changed the FROM expression: {source}")
            query = (f"{category}__tpcds__{namespace}__{template['name']}__"
                     f"{template['join_vector'].lower()}__{template['expression_fingerprint'][:8]}__sel_{tier}")
            source_label = f"{template['source_benchmark']} {template['source_query']}".rstrip()
            content = (f"-- corpus_revision: {b.REVISION}; component: {spec['revision']}\n"
                       f"-- historical_pattern: {template['historical_query']}\n"
                       f"-- source: {source_label}\n"
                       f"-- selectivity: {tier}; frozen base-entity calibration, not joined output\n"
                       "-- policy: performance-conditioned historical recovery; pending cpu9 measurement\n"
                       "-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; "
                       f"projection={template['projection_policy']}\n" + sql)
            row = dict(metadata, family="tpcds", source_seed=template["source_seed"],
                       source_benchmark=template["source_benchmark"], source_query=template["source_query"],
                       source_location=str(source.relative_to(b.legacy.REPO_ROOT)),
                       source_sha256=template["archive_sha256"], benchmark_source_location=template["source_location"],
                       source_filter_adaptation="Archived join types/grouping/keys and filter relation retained; WHERE replaced by three cohorts; historical timings not reused",
                       topology=template["topology"], tree_shape=template["tree_shape"],
                       join_vector=template["join_vector"], relation_count=template["relation_count"],
                       expression_fingerprint=template["expression_fingerprint"],
                       provenance_class="industry_synthetic_control" if control else "historical_pattern_adaptation",
                       source_component=component, evaluation_role=role,
                       query_id=query, path=f"tpcds/{query}.sql", query_class=category, workload_category=category,
                       corpus_revision=b.REVISION, sql_fingerprint=b.sql_fingerprint(sql, "tpcds"),
                       aggregate_variant=aggregate, aggregate_anchor="", selectivity_stress="false",
                       regression_guard="false", candidate_batch=0, qualification_status="PENDING_CPU9_MEASUREMENT",
                       qualification_timeout_seconds=b.QUALIFICATION_TIMEOUT_SECONDS,
                       qualification_min_runtime_s=0, qualification_min_speedup=.5,
                       **{revision_key: spec["revision"], template_key: template["name"]},
                       historical_source_sql=template["archive_sql"], historical_source_query=template["historical_query"],
                       historical_source_run=template["historical_run"], historical_projection_policy=template["projection_policy"],
                       content_sha256=hashlib.sha256(content.encode()).hexdigest())
            yield row, content


def apply(records, output):
    """Apply exact-query exclusions only; keep other tiers and families intact."""
    spec = policy()
    excluded = {r["sql_fingerprint"]: r for r in spec["excluded"]}
    retained, removed = [], []
    for row in records:
        match = excluded.get(row["sql_fingerprint"]) if row["family"] == "tpcds" else None
        if match:
            if row["query_id"] != match["query_id"] or row["content_sha256"] != match["content_sha256"]:
                raise ValueError(f"Exclusion evidence no longer matches: {row['query_id']}")
            (output / row["path"]).unlink()  # only staged, newly generated SQL
            removed.append(match)
            continue
        if row["family"] == "tpcds":
            row.update(tpcds_refresh_revision=spec["revision"], qualification_min_runtime_s=0,
                       qualification_min_speedup=.5)
        retained.append(row)
    if len(removed) != spec["expected_exclusions"]:
        raise ValueError("TPC-DS exclusion set does not match the pinned primary batch")
    identities = {r["sql_fingerprint"] for r in retained}
    new = list(recovery_queries())
    known_bad = {r["sql_fingerprint"] for r in spec["recovery_rejected_exact_sql"]}
    for row, sql in new:
        if row["sql_fingerprint"] in identities or row["sql_fingerprint"] in excluded or row["sql_fingerprint"] in known_bad:
            raise ValueError(f"Duplicate or excluded recovery SQL: {row['query_id']}")
        identities.add(row["sql_fingerprint"])
        (output / row["path"]).write_text(sql, encoding="utf-8")
        retained.append(row)
    b.write_json(output / MARKER, dict(revision=spec["revision"], policy_sha256=b.digest(POLICY),
        target_complete_pairs=spec["target_complete_pairs"], retained_previous_measured_pairs=7,
        new_candidates=len(new), removed_queries=len(removed), status="PENDING_CPU9_MEASUREMENT",
        counts=dict(Counter(r["family"] for r in retained)),
        note="Measured-pair target is not guaranteed. Historical selection and exclusions must be disclosed."))
    b.write_csv(output / "tpcds_excluded.csv", removed)
    (output / "tpcds_recovery.txt").write_text("".join(r["path"] + "\n" for r, _ in new), encoding="utf-8")
    return retained


def archive_retired(destination, old_rows, root, *, exclusions=None, revision="retired_tpcds_20261005"):
    """Preserve removed SQL and old manifest rows before active-set replacement."""
    excluded = {r["query_id"]: r for r in (policy()["excluded"] if exclusions is None else exclusions)}
    rows = [r for r in old_rows if r["query_id"] in excluded]
    if not rows:
        return
    archive = root / "revisions" / revision / "benchmark"
    for row in rows:
        source, target = destination / row["path"], archive / row["path"]
        if b.digest(source) != excluded[row["query_id"]]["content_sha256"]:
            raise ValueError(f"Refusing to retire locally edited SQL: {source}")
        if target.exists() and b.digest(target) != b.digest(source):
            raise ValueError(f"Retired archive differs: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
    manifest = archive / "manifest.csv"
    if manifest.exists():
        if b.read_manifest(manifest) != rows:
            raise ValueError("Retired manifest differs; refusing overwrite")
    else:
        b.write_csv(manifest, rows)


def validate(benchmark, rows):
    spec = policy()
    marker = json.loads((benchmark / MARKER).read_text(encoding="utf-8"))
    if marker["policy_sha256"] != b.digest(POLICY) or marker["revision"] != spec["revision"]:
        raise ValueError("TPC-DS refresh policy changed; regenerate")
    counts = dict(Counter(r["family"] for r in rows))
    expected = dict(graph=180, tpch=180, tpcds=spec["expected_tpcds_total"], job=180)
    if counts != expected or marker["counts"] != counts:
        raise ValueError("TPC-DS refresh counts do not match the pinned design")
    excluded = {r["sql_fingerprint"] for r in spec["excluded"]}
    if any(r["sql_fingerprint"] in excluded for r in rows):
        raise ValueError("An excluded exact SQL query was restored")
    expected_new = {r["query_id"]: r for r, _ in recovery_queries()}
    actual = [r for r in rows if is_recovery(r)]
    if len(actual) != spec["expected_new_candidates"] or set(expected_new) != {r["query_id"] for r in actual}:
        raise ValueError("Incomplete historical recovery triples")
    for row in actual:
        if any(str(row.get(k, "")) != str(v) for k, v in expected_new[row["query_id"]].items()):
            raise ValueError(f"Recovery metadata changed: {row['query_id']}")
        if row["sql_fingerprint"] in {r["sql_fingerprint"] for r in spec["recovery_rejected_exact_sql"]}:
            raise ValueError(f"Recovery renamed a known failed SQL query: {row['query_id']}")
    unaffected = [r for r in rows if r["family"] != "tpcds"]
    cells = Counter((r["family"], r["tree_shape"], r["semantic_tier"]) for r in unaffected)
    if cells != {(f, s, t): 20 for f in ("graph", "tpch", "job") for s in b.SHAPES for t in b.TIERS}:
        raise ValueError("TPC-DS refresh changed another family's quotas")
