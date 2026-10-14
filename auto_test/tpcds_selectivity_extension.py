"""Pinned historical and source-subgraph patterns expanded into three-band candidates.

This overlay follows the frozen exact-SQL screens. Historical measurements are
selection provenance only; generation never reads or changes raw results.
"""
from collections import Counter
import json
import math
from pathlib import Path
import re

import balanced_benchmark as b
import benchmark_speedup_screen as screen
from benchmark_corpus import count_base_relations
import tpcds_refresh as refresh
from workload_policy import REPRESENTATION

POLICY = b.ROOT / "sources/tpcds_extension_20261008_r2.json"
ROLE = "historical_selectivity_extension"
NAMESPACE = "extension_20261008"
MARKER = "tpcds_extension.json"
QUERY_LIST = "tpcds_extension.txt"


def is_extension(row):
    return row.get("evaluation_role") == ROLE


def historical_eligible(template, threshold):
    """Select from complete historical evidence using the unrounded ratio."""
    if (template.get("historical_correct") != "TRUE" or str(template.get("historical_selected")) != "1"
            or template.get("historical_timing_status") != "measured"):
        return False
    try:
        off, on = float(template["historical_duckdb_s"]), float(template["historical_outeryan_s"])
    except (KeyError, TypeError, ValueError):
        return False
    if not all(math.isfinite(value) and value > 0 for value in (off, on)):
        return False
    ratio = off / on
    return math.isfinite(ratio) and ratio >= threshold


def policy():
    spec = json.loads(POLICY.read_text(encoding="utf-8"))
    if spec.get("representation") != REPRESENTATION:
        raise ValueError("Expected a frozen TPC-DS workload definition")
    threshold = float(spec["historical_selection_min_speedup"])
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("Invalid TPC-DS historical selection threshold")
    templates = spec["templates"]
    if not templates or spec["expected_new_candidates"] != len(templates) * len(b.TIERS):
        raise ValueError("TPC-DS extension must contain complete three-tier groups")
    if spec["expected_counts_before"] != screen.policy()["expected_counts_after"]:
        raise ValueError("TPC-DS extension no longer matches the frozen screened corpus")
    expected = dict(spec["expected_counts_before"])
    expected["tpcds"] += spec["expected_new_candidates"]
    if spec["expected_counts_after"] != expected:
        raise ValueError("TPC-DS extension counts do not match its templates")
    previous_policy = b.ROOT / spec["previous_policy"]
    if b.digest(previous_policy) != spec["previous_policy_sha256"]:
        raise ValueError("TPC-DS extension predecessor policy changed")
    retired = spec["retired_queries"]
    if len(retired) != 6 or len({r["query_id"] for r in retired}) != 6:
        raise ValueError("TPC-DS extension retirement requires the exact six r1 queries")
    names, patterns = set(), set()
    previous = {(t["expression_fingerprint"], t["aggregate_variant"])
                for t in refresh.policy()["templates"]}
    for template in templates:
        derived = template.get("source_kind") == "source_connected_subgraph"
        name = template["name"]
        source = Path(template["template_sql"] if derived else template["archive_sql"])
        pattern = (template["expression_fingerprint"], template["aggregate_variant"])
        if not re.fullmatch(r"[a-z0-9_]+", name) or name in names:
            raise ValueError("Invalid or duplicate TPC-DS extension template name")
        expected_parent = "sources" if derived else "revisions"
        if source.is_absolute() or ".." in source.parts or not source.parts or source.parts[0] != expected_parent:
            raise ValueError("Unsafe TPC-DS extension archive path")
        if derived:
            original = b.legacy.REPO_ROOT / template["source_location"]
            if b.digest(original) != template["original_source_sha256"]:
                raise ValueError(f"Connected-subgraph benchmark source changed: {original}")
            if any(key.startswith("historical_") for key in template):
                raise ValueError("New connected-subgraph SQL cannot inherit historical measurements")
        if pattern in patterns or pattern in previous:
            raise ValueError("TPC-DS extension repeats an existing historical pattern")
        names.add(name)
        patterns.add(pattern)
    return spec


def extension_queries(spec=None):
    spec = policy() if spec is None else spec
    for template in spec["templates"]:
        derived = template.get("source_kind") == "source_connected_subgraph"
        generation = dict(spec, templates=[template], revision=template.get("generation_revision", spec["revision"]))
        yield from refresh.recovery_queries(
            generation, role=ROLE, namespace=template.get("namespace", NAMESPACE), component="historical_extension",
            revision_key="tpcds_extension_revision", template_key="extension_template",
            parameter_policy=("Source-connected single-fact subgraph; fixed 3/30/55 base-entity cohorts "
                              "on the customer relation; CPU9 audit required" if derived else
                              "Historical-performance-selected pattern; fixed 3/30/55 base-entity cohorts "
                              "on the old filter relation; CPU9 audit required"))


def archive_retired(destination, old_rows, root):
    """Archive the exact six r1 SQL files before replacing the active corpus."""
    spec = policy()
    refresh.archive_retired(destination, old_rows, root, exclusions=spec["retired_queries"],
                            revision=spec["retirement_revision"])


def excluded_fingerprints():
    old = refresh.policy()
    return {row["sql_fingerprint"] for row in
            old["excluded"] + old["recovery_rejected_exact_sql"] + screen.policy()["excluded"]
            + policy()["retired_queries"]}


def _marker(spec, records):
    return dict(revision=spec["revision"], policy_sha256=b.digest(POLICY),
                target_complete_pairs=spec["target_complete_pairs"],
                new_candidates=spec["expected_new_candidates"],
                status="PENDING_CPU9_MEASUREMENT", counts=dict(Counter(r["family"] for r in records)),
                note="New three-band SQL requires CPU9 selectivity audit and bare-query ON/OFF measurement. "
                     "Historical runtimes are selection provenance, not results for these candidates.")


def apply(records, output):
    """Append candidates without changing the screened queries or their policy."""
    spec = policy()
    if dict(Counter(r["family"] for r in records)) != spec["expected_counts_before"]:
        raise ValueError("TPC-DS extension input counts do not match the frozen corpus")
    identities = {r["sql_fingerprint"] for r in records} | excluded_fingerprints()
    query_ids = {r["query_id"] for r in records}
    paths = {r["path"] for r in records}
    additions = list(extension_queries(spec))
    for row, sql in additions:
        if row["sql_fingerprint"] in identities or row["query_id"] in query_ids or row["path"] in paths:
            raise ValueError(f"Duplicate or excluded extension SQL: {row['query_id']}")
        if count_base_relations(sql) != int(row["relation_count"]):
            raise ValueError(f"Extension relation count changed: {row['query_id']}")
        identities.add(row["sql_fingerprint"])
        query_ids.add(row["query_id"])
        paths.add(row["path"])
    retained = records + [row for row, _ in additions]
    for row, sql in additions:
        (output / row["path"]).write_text(sql, encoding="utf-8")
    b.write_json(output / MARKER, _marker(spec, retained))
    (output / QUERY_LIST).write_text("".join(r["path"] + "\n" for r, _ in additions), encoding="utf-8")
    return retained


def validate(benchmark, rows):
    """Validate the overlay, then return the unchanged earlier screened cohort."""
    spec = policy()
    marker = json.loads((benchmark / MARKER).read_text(encoding="utf-8"))
    if marker != _marker(spec, rows) or marker["counts"] != spec["expected_counts_after"]:
        raise ValueError("TPC-DS extension policy or counts changed; regenerate")
    additions = list(extension_queries(spec))
    expected = {r["query_id"]: r for r, _ in additions}
    actual = [r for r in rows if is_extension(r)]
    if len(actual) != spec["expected_new_candidates"] or set(expected) != {r["query_id"] for r in actual}:
        raise ValueError("Incomplete TPC-DS extension triples")
    excluded = excluded_fingerprints()
    for row in actual:
        if any(str(row.get(key, "")) != str(value) for key, value in expected[row["query_id"]].items()):
            raise ValueError(f"Extension metadata changed: {row['query_id']}")
        if row["sql_fingerprint"] in excluded:
            raise ValueError(f"Extension restored an excluded exact SQL query: {row['query_id']}")
    expected_list = "".join(r["path"] + "\n" for r, _ in additions)
    if (benchmark / QUERY_LIST).read_text(encoding="utf-8") != expected_list:
        raise ValueError("TPC-DS extension query list changed")
    original = [r for r in rows if not is_extension(r)]
    if dict(Counter(r["family"] for r in original)) != spec["expected_counts_before"]:
        raise ValueError("TPC-DS extension changed the earlier screened corpus")
    return original
