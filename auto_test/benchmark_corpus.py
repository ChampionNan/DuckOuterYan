"""Shared SQL identities and paths for the deduplicated benchmark (Python 3.7+)."""

import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "outerjoin_benchmark"
ARCHIVE_NAME = "semantic_ranges_20260929"
HISTORICAL_SCOPES = {
    "v1": "benchmark", "v2": "v2/benchmark",
    "v3_aggregation": "v3/benchmark", "v3_selectivity_stress": "v3/selectivity_stress",
    "v2_job_regressions": "v2/job_regressions",
}
SQL_TOKEN = re.compile(
    r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*[\s\S]*?\*/"
    r"|[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?|<>|<=|>=|!=|[^\s]"
)


def sql_fingerprint(sql, family):
    """Ignore comments/formatting, preserving literals, join kinds and grouping."""
    tokens = [token if token.startswith(("'", '"')) else token.lower()
              for token in SQL_TOKEN.findall(sql) if not token.startswith(("--", "/*"))]
    family = {"tpc-h": "tpch", "tpc-ds": "tpcds"}.get(family.lower(), family.lower())
    payload = json.dumps([family, tokens], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def count_base_relations(sql):
    """Count generated join leaves, excluding input-filter SELECT wrappers.

    Supports the corpus's explicit join trees and scan subqueries, not arbitrary
    SQL (e.g. CTE expansion or comma-separated FROM lists).
    """
    tokens = [t.lower() for t in SQL_TOKEN.findall(sql) if not t.startswith(("--", "/*"))]
    count = 0
    for i, token in enumerate(tokens):
        if token not in ("from", "join"):
            continue
        j = i + 1
        while j < len(tokens) and tokens[j] == "(":
            j += 1
        if j < len(tokens) and tokens[j] not in ("select", "with"):
            count += 1
    return count


def read_manifest(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def historical_manifests(root=ROOT):
    """Oldest first, so newer definitions take precedence for the same old ID."""
    for revision in ("pre_semantic_20260925", ARCHIVE_NAME):
        for category, scope in HISTORICAL_SCOPES.items():
            path = root / "revisions" / revision / scope / "manifest.csv"
            if path.is_file():
                yield category, path
    for revision in ("unique_semantic_20260929", "retired_tpcds_20261005",
                     "retired_speedup_20261005", "retired_speedup_20261007", "retired_speedup_20261008",
                     "retired_tpcds_extension_20261008_r1", "retired_aggregate_count_20261008"):
        path = root / "revisions" / revision / "benchmark/manifest.csv"
        if path.is_file():
            yield None, path


def resolve_sql_path(category, relative, root=ROOT):
    path = Path(relative)
    if ".." in path.parts:
        raise ValueError("Unsafe SQL path: " + str(path))
    if path.is_absolute():
        if path.is_file():
            return path
        raise FileNotFoundError(path)
    scope = HISTORICAL_SCOPES.get(category, "benchmark")
    if category in HISTORICAL_SCOPES:
        candidates = [root / "revisions" / revision / scope / path
                      for revision in (ARCHIVE_NAME, "pre_semantic_20260925")]
        candidates.append(root / scope / path)
    else:
        candidates = [root / "benchmark" / path]
        candidates.append(root / "revisions/unique_semantic_20260929/benchmark" / path)
        candidates.append(root / "revisions/retired_tpcds_20261005/benchmark" / path)
        candidates.append(root / "revisions/retired_speedup_20261005/benchmark" / path)
        candidates.append(root / "revisions/retired_speedup_20261007/benchmark" / path)
        candidates.append(root / "revisions/retired_speedup_20261008/benchmark" / path)
        candidates.append(root / "revisions/retired_tpcds_extension_20261008_r1/benchmark" / path)
        candidates.append(root / "revisions/retired_aggregate_count_20261008/benchmark" / path)
        # The former query-type prefix is a naming alias; SQL identity is unchanged.
        if path.name.startswith("control__"):
            candidates.append(root / "benchmark" / path.with_name(
                "graph__" + path.name[len("control__"):]))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(candidates[0])


def canonical_query_id(row):
    """Readable type/family/source/structure/filter ID, without suite versions."""
    kind = ("aggregate" if row.get("aggregate_variant") else
            "join" if row.get("source_component") == "core" else "graph")
    base = row.get("base_query_id") or row["query_id"]
    base = re.sub(r"^(?:derived|industry|aggregate|stress)__(?:sem__)?", "", base)
    base = re.sub(r"^(?:ojb_|oy_)", "", base)
    family = row["family"]
    base = re.sub(r"^(?:" + family + r"_|jb_jb_|th_th_|td_td_)", "", base)
    base = re.sub(r"_(?:sel|stress)_(?:low|medium|high)$", "", base)
    base = re.sub(r"_v\d+(?=_|$)", "", base)
    parts = [kind, family, base, row.get("join_vector", "").lower()]
    if row.get("aggregate_variant"):
        parts.append(row["aggregate_variant"])
    parts.append("sel_" + row["semantic_tier"])
    return "__".join(re.sub(r"[^a-z0-9_]+", "_", part.lower()).strip("_")
                     for part in parts if part)
