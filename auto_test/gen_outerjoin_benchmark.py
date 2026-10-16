#!/usr/bin/env python3
"""Generate the provenance-backed OuterJoin benchmark corpus.

Generation reads frozen source definitions and approved policies, never local
timing results. The active workload is historically performance-conditioned;
deterministic regeneration does not make it an independently selected sample.
Each seed records an upstream benchmark query and retains a connected subgraph of its
relation instances and join predicates.  The SQL is normalized to a flat
projection/filter/join skeleton so that it remains inside the optimizer's
current applicability envelope. Aggregate variants replace only the projection
with a root aggregation while preserving the same source graph.

The active ``benchmark`` corpus contains each SQL identity once, across join, graph and aggregate queries.
Query names describe type, execution family, source/structure, join kinds and filter band.
Historical suite names are retained only in aliases and archived definitions.
The balanced generator applies the frozen transformations in a temporary directory
and verifies the published definitions before replacing an active workload.

"""

from __future__ import annotations

import argparse
import csv
import datetime as datetime_module
import hashlib
import json
import os
import re
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from benchmark_corpus import sql_fingerprint

from legacy_corpus import COMPLETED_QUERY_PATHS, REFERENCE_RUN


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_ROOT = SCRIPT_DIR / "outerjoin_benchmark"
DEFAULT_V2_ROOT = DEFAULT_ROOT / "v2"
DEFAULT_V3_ROOT = DEFAULT_ROOT / "v3"
CORE_QUERY_COUNT = 170
GRAPH_CONTROL_FILENAMES = tuple(
    Path(path).name
    for path in sorted(COMPLETED_QUERY_PATHS)
    if Path(path).parts[0] == "graph"
)
GRAPH_CONTROL_QUERY_COUNT = 25
if len(GRAPH_CONTROL_FILENAMES) != GRAPH_CONTROL_QUERY_COUNT:
    raise RuntimeError(
        f"expected {GRAPH_CONTROL_QUERY_COUNT} completed graph controls, "
        f"found {len(GRAPH_CONTROL_FILENAMES)}"
    )
INDUSTRY_EVALUATION_QUERY_COUNT = 54
SEMANTIC_DESIGN_PATH = DEFAULT_ROOT / "sources" / "semantic_filter_design.json"
SEMANTIC_DESIGN = json.loads(SEMANTIC_DESIGN_PATH.read_text(encoding="utf-8"))
SEMANTIC_TIERS = tuple(row["name"] for row in SEMANTIC_DESIGN["tiers"])
V1_CORPUS_REVISION = SEMANTIC_DESIGN["revision"]
ACTIVE_CORE_QUERY_COUNT = CORE_QUERY_COUNT
ACTIVE_BENCHMARK_QUERY_COUNT = CORE_QUERY_COUNT + INDUSTRY_EVALUATION_QUERY_COUNT
V2_SELECTIVITY_TIERS = tuple(
    (f"sel_{row['name']}", row["target_fraction"],
     f"{100 * row['lower_bound']:g}–{100 * row['upper_bound']:g}% of the calibration population")
    for row in SEMANTIC_DESIGN["tiers"]
)
V2_CORE_QUERY_COUNT = CORE_QUERY_COUNT * len(V2_SELECTIVITY_TIERS)
V2_EVALUATION_QUERY_COUNT = ACTIVE_BENCHMARK_QUERY_COUNT - ACTIVE_CORE_QUERY_COUNT
V2_BENCHMARK_QUERY_COUNT = V2_CORE_QUERY_COUNT + V2_EVALUATION_QUERY_COUNT
V2_0916_REFERENCE_RUN = "experiment_onoff_benchmark_20260916_211812_t32.csv"
SELECTIVITY_STRESS_TIERS = tuple(
    (f"stress_{name}", name, target, description)
    for name, (_, target, description) in zip(SEMANTIC_TIERS, V2_SELECTIVITY_TIERS)
)
SELECTIVITY_STRESS_FAMILIES = ("tpch", "tpcds", "job")
SELECTIVITY_STRESS_TREE_SHAPES = ("left_deep", "right_deep", "bushy")
SELECTIVITY_STRESS_MIN_RELATIONS = 4
# Six paired bases keep the ablation below 50 queries while balancing both
# family (two per family) and tree shape (two per shape) over the complete set.
V3_STRESS_SLOTS_BY_FAMILY = {
    "tpch": (("left_deep", "TPC-H"), ("right_deep", "SQLStorm")),
    "tpcds": (("right_deep", "TPC-DS"), ("bushy", "SQLStorm")),
    "job": (("bushy", "JOB"), ("left_deep", "SQLStorm")),
}
V3_STRESS_BASES_PER_FAMILY = 2
V3_STRESS_BASE_COUNT = (
    len(SELECTIVITY_STRESS_FAMILIES) * V3_STRESS_BASES_PER_FAMILY
)
V3_STRESS_QUERY_COUNT = V3_STRESS_BASE_COUNT * len(SELECTIVITY_STRESS_TIERS)
V3_STRESS_SELECTION_SALT = "outeryan-v3-semantic-selectivity-v1"
V2_JOB_REGRESSIONS: tuple[tuple[str, str], ...] = (
    ("ojb_sqlstorm_job_11914_bdmx", "1af32617cb10164c5f999a0f99f196b23232059a40dd8f0f2ff5e1eb81af7836"),
    ("oy_jb_jb_bushy4a_v2", "6dca40cd9267b67ea297a5245c6cd0d9b0fe7bf8653d1d6c6a643f89e9a82103"),
)
V2_JOB_REGRESSION_COUNT = len(V2_JOB_REGRESSIONS)
V3_VARIANTS_PER_SEED = 3
V3_BENCHMARK_QUERY_COUNT = 102
V3_AGGREGATE_TARGET_COUNTS = {
    # COUNT is intentionally the largest class. MIN and MAX are two operators
    # for the same extremum workload class, so they split that class equally.
    # SUM remains a substantial control class, but is smaller than COUNT.
    "global_count": 42,
    "grouped_sum": 30,
    "grouped_min": 15,
    "grouped_max": 15,
}
V3_AGGREGATE_VARIANTS = tuple(V3_AGGREGATE_TARGET_COUNTS)
if sum(V3_AGGREGATE_TARGET_COUNTS.values()) != V3_BENCHMARK_QUERY_COUNT:
    raise RuntimeError("v3 aggregate targets must sum to the v3 benchmark size")
# Approved 32-thread timeouts move topology/scale/vector shares by up to 2.66 pp.
# Tree-shape shares still satisfy the original 2 pp bound. Do not remove healthy
# queries merely to rebalance counts; retain explicit coverage-loss accounting.
MAX_CORE_PATTERN_SHARE_SHIFT = 0.03
LEGACY_WIN_SELECTION_POLICY = (
    f"{REFERENCE_RUN}: correct=TRUE; "
    "selected_plan=OUTERYAN; tm_speedup>1.0"
)
ACTIVE_LEGACY_SOURCE_SELECTION_POLICY = (
    LEGACY_WIN_SELECTION_POLICY + "; archived source query before active normalization"
)
GRAPH_CONTROL_SELECTION_POLICY = (
    "all 25 completed legacy graph-generator patterns; no timing-based selection"
)

INDUSTRY_INSPIRED_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    (
        "tpch",
        "oy_th_real_cust_order_line.sql",
        "optional_fact_enrichment",
        "Customer master records retain optional orders, line items, and geography.",
    ),
    (
        "tpch",
        "oy_th_real_custdist.sql",
        "completeness_detail",
        "Customer activity detail retains customers without order lines.",
    ),
    (
        "tpch",
        "oy_th_real_supplier_catalog.sql",
        "optional_catalog_enrichment",
        "Supplier masters retain optional catalog, part, and geographic attributes.",
    ),
    (
        "tpch",
        "oy_th_real_supplier_right.sql",
        "right_preserved_master",
        "A right outer join preserves suppliers before optional catalog enrichment.",
    ),
    (
        "tpcds",
        "oy_ds_real_catalog_demo.sql",
        "optional_demographic_enrichment",
        "Catalog facts retain optional customer, demographic, and item context.",
    ),
    (
        "tpcds",
        "oy_ds_real_store_agg.sql",
        "dimension_coverage_detail",
        "Store activity detail retains optional item, store, and customer dimensions.",
    ),
    (
        "tpcds",
        "oy_ds_real_store_demo.sql",
        "sparse_profile_enrichment",
        "Store facts retain sparse demographic, household, and address annotations.",
    ),
    (
        "tpcds",
        "oy_ds_real_store_dims.sql",
        "optional_dimension_enrichment",
        "Store facts retain optional item, customer, store, and promotion dimensions.",
    ),
    (
        "tpcds",
        "oy_ds_real_web_geo.sql",
        "optional_geographic_enrichment",
        "Web facts retain optional customer, address, and date context.",
    ),
)

SQLSTORM_COMMIT = "b3bb0b96794a6afe9bb8f3ff2b243562b779c40d"

JOIN_SQL = {
    "I": "INNER JOIN",
    "L": "LEFT OUTER JOIN",
    "R": "RIGHT OUTER JOIN",
    "F": "FULL OUTER JOIN",
}

MIXED_JOIN_CYCLE: tuple[str, ...] = ("I", "L", "R", "F")
JOIN_KEYWORD_PATTERN = re.compile(
    r"\b(?:INNER|LEFT(?:\s+OUTER)?|RIGHT(?:\s+OUTER)?|FULL(?:\s+OUTER)?)\s+JOIN\b",
    re.IGNORECASE,
)
SOURCE_BENCHMARKS = frozenset({"TPC-H", "TPC-DS", "JOB", "SQLStorm"})


def semantic_filter(profile_id: str, column: str, tier: str) -> str:
    """Render a frozen, interpretable business cohort, never a key sample."""
    profile = SEMANTIC_DESIGN["profiles"][profile_id]
    index = SEMANTIC_TIERS.index(tier)
    if profile["kind"] == "predicates":
        return profile["predicates"][index].format(column=column)
    bound = profile["bounds"][index]
    if profile["kind"] == "date_window":
        center = datetime_module.date.fromisoformat(profile["pivot"])
        radius = datetime_module.timedelta(days=int(bound))
        return f"{column} BETWEEN DATE '{center - radius}' AND DATE '{center + radius}'"
    operator, value = (">=", -bound) if profile["kind"] == "lower" else ("<=", bound)
    return f"{column} {operator} {value:.10g}"


def semantic_metadata(profile_id: str, column: str, tier: str) -> dict[str, str]:
    profile = SEMANTIC_DESIGN["profiles"][profile_id]
    calibration = profile["calibration"]
    index = SEMANTIC_TIERS.index(tier)
    spec = SEMANTIC_DESIGN["tiers"][index]
    target, lower, upper = (spec[key] for key in
                            ("target_fraction", "lower_bound", "upper_bound"))
    qualified = calibration["qualified_rows"][index]
    observed = qualified / calibration["n"]
    return {
        "filter_design_revision": V1_CORPUS_REVISION,
        "selectivity_tier": f"sel_{tier}",
        "semantic_tier": tier,
        "target_fraction": f"{target:.6f}",
        "target_min_fraction": f"{lower:.6f}",
        "target_max_fraction": f"{upper:.6f}",
        "target_min_inclusive": str(spec["include_lower"]).lower(),
        "target_max_inclusive": str(spec["include_upper"]).lower(),
        "selectivity_profile": profile_id,
        "selectivity_anchor": column,
        "selectivity_predicate": semantic_filter(profile_id, column, tier),
        "filter_semantics": profile["meaning"],
        "selectivity_denominator": profile["calibration_from"],
        "calibration_rows": str(calibration["n"]),
        "calibration_qualified_rows": str(qualified),
        "calibration_fraction": f"{observed:.9f}",
        "calibration_in_range": str(fraction_in_band(observed, spec)).lower(),
        "selectivity_scope": "base entity (including NULLs in denominator), not joined output",
        "parameter_policy": "frozen business literals; replace full WHERE; no runtime-based selection",
        "source_filter_adaptation": "synthetic control with a business range on its base entity",
    }


def seed_filter_metadata(seed: Seed, tier: str | None = None) -> dict[str, str]:
    spec = SEMANTIC_DESIGN["seeds"][seed.seed_id]
    metadata = semantic_metadata(spec["profile"], spec["column"], tier or spec["default_tier"])
    metadata["source_filter_adaptation"] = spec["adaptation"]
    return metadata


def fraction_in_band(value: float, spec: dict) -> bool:
    lower_ok = value >= spec["lower_bound"] if spec["include_lower"] else value > spec["lower_bound"]
    upper_ok = value <= spec["upper_bound"] if spec["include_upper"] else value < spec["upper_bound"]
    return lower_ok and upper_ok


def replace_where(sql: str, predicate: str) -> str:
    result, count = re.subn(r"\bWHERE\s+.*?(?=\s+GROUP\s+BY\b|;)",
                            lambda _: f"WHERE {predicate}", sql, count=1,
                            flags=re.IGNORECASE | re.DOTALL)
    if count != 1:
        raise ValueError("Expected one outer WHERE clause when replacing the semantic cohort")
    return result


def validate_semantic_query(sql: str, row: dict[str, str]) -> None:
    """Check the emitted predicate, not just its provenance comment."""
    statement = re.sub(r"--[^\n]*", "", sql)
    operators = re.sub(r"'(?:''|[^'])*'", "''", statement)
    if re.search(r"%|\b(?:MOD|HASH)\s*\(", operators, re.IGNORECASE):
        raise RuntimeError(f"{row['path']}: key sampling is not a semantic filter")
    where = re.search(r"\bWHERE\s+(.*?)(?=\s+GROUP\s+BY\b|;)",
                      statement, re.IGNORECASE | re.DOTALL)
    if not where or where.group(1).strip() != row["selectivity_predicate"]:
        raise RuntimeError(f"{row['path']}: WHERE differs from the declared business cohort")
    if (row["filter_design_revision"] != V1_CORPUS_REVISION
            or row["calibration_in_range"] != "true"):
        raise RuntimeError(f"{row['path']}: stale or out-of-band calibration")


ACTIVE_JOIN_SQL = "FULL OUTER JOIN"
SIMPLE_EDGE_EQUALITY = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)"
)
ACTIVE_AGGREGATE_SOURCES = {
    ("tpch", "oy_th_real_custdist.sql"),
    ("tpcds", "oy_ds_real_store_agg.sql"),
}


@dataclass(frozen=True)
class Seed:
    family: str
    seed_id: str
    source_benchmark: str
    source_version: str
    source_query: str
    source_location: str
    source_hash: str
    topology: str
    semantics: str
    relations: tuple[str, ...]
    predicates: tuple[str, ...]
    projection: str
    semantic_vector: tuple[str, ...]

    @property
    def where(self) -> str:
        return seed_filter_metadata(self)["selectivity_predicate"]

    def validate(self) -> None:
        edge_count = len(self.relations) - 1
        if edge_count < 2:
            raise ValueError(f"{self.seed_id}: at least three relations are required")
        if len(self.predicates) != edge_count:
            raise ValueError(f"{self.seed_id}: relation/predicate count mismatch")
        if len(self.semantic_vector) != edge_count:
            raise ValueError(f"{self.seed_id}: semantic-vector length mismatch")
        if any(kind not in JOIN_SQL for kind in self.semantic_vector):
            raise ValueError(f"{self.seed_id}: invalid semantic join kind")
        if "ON 1=1" in " ".join(self.predicates).upper():
            raise ValueError(f"{self.seed_id}: cross products are not allowed")
        actual_topology = classify_topology(self.predicates)
        if self.topology != actual_topology:
            raise ValueError(
                f"{self.seed_id}: topology is {self.topology}, expected {actual_topology}"
            )


def is_dataless(path: Path) -> bool:
    """Return whether macOS File Provider has evicted this file's contents."""
    dataless_flag = getattr(stat, "SF_DATALESS", 0)
    return bool(dataless_flag and path.stat().st_flags & dataless_flag)


def pinned_source_hashes() -> dict[str, str]:
    """Read source pins from the checked-in manifest without hydrating sources."""
    manifest = DEFAULT_ROOT / "manifest.csv"
    if not manifest.is_file() or is_dataless(manifest):
        return {}
    with manifest.open(newline="", encoding="utf-8") as handle:
        return {
            row["source_location"]: row["source_sha256"]
            for row in csv.DictReader(handle)
        }


PINNED_SOURCE_HASHES = pinned_source_hashes()


def file_sha256(relative_path: str) -> str:
    source = REPO_ROOT / relative_path
    if is_dataless(source):
        pinned = PINNED_SOURCE_HASHES.get(relative_path)
        if pinned:
            return pinned
        raise RuntimeError(
            f"source is an iCloud placeholder and has no manifest pin: {source}"
        )
    return hashlib.sha256(source.read_bytes()).hexdigest()


def mixed_vector(edge_count: int, offset: int = 0) -> tuple[str, ...]:
    """Systematic mixed labeling, independent of observed performance."""
    pattern = ("I", "L", "F", "R")
    return tuple(pattern[(offset + i) % len(pattern)] for i in range(edge_count))


def compact_seed(
    *,
    family: str,
    seed_id: str,
    source_benchmark: str,
    source_version: str,
    source_query: str,
    source_location: str,
    topology: str,
    semantics: str,
    relations: Sequence[str],
    predicates: Sequence[str],
    offset: int = 0,
) -> Seed:
    return Seed(
        family=family,
        seed_id=seed_id,
        source_benchmark=source_benchmark,
        source_version=source_version,
        source_query=source_query,
        source_location=source_location,
        source_hash=file_sha256(source_location),
        topology=topology,
        semantics=semantics,
        relations=tuple(relations),
        predicates=tuple(predicates),
        projection="*",
        semantic_vector=mixed_vector(len(relations) - 1, offset),
    )


def predicate_aliases(predicate: str) -> tuple[str, str]:
    refs = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\.[A-Za-z_][A-Za-z0-9_]*", predicate)
    distinct = list(dict.fromkeys(refs))
    if len(distinct) < 2:
        raise ValueError(f"join predicate does not reference two aliases: {predicate}")
    return distinct[0], distinct[1]


def classify_topology(predicates: Sequence[str]) -> str:
    degree: dict[str, int] = {}
    for predicate in predicates:
        left, right = predicate_aliases(predicate)
        degree[left] = degree.get(left, 0) + 1
        degree[right] = degree.get(right, 0) + 1
    maximum = max(degree.values(), default=0)
    if len(degree) >= 4 and maximum == len(degree) - 1:
        return "star"
    return "branch" if maximum >= 3 else "chain"


def generated_seed_skeleton(family: str, seed_id: str) -> tuple[list[str], list[str], str]:
    """Recover a checked-in seed skeleton without hydrating its source file."""
    generated = DEFAULT_ROOT / "core" / family / f"ojb_{seed_id}_ldmx.sql"
    if not generated.is_file() or is_dataless(generated):
        raise RuntimeError(
            f"source and generated fallback are both iCloud placeholders: {generated}"
        )
    text = generated.read_text(encoding="utf-8")
    first = re.search(
        r"\bFROM\s+\(*\s*([A-Za-z_][A-Za-z0-9_]*)\s+(?:AS\s+)?"
        r"([A-Za-z_][A-Za-z0-9_]*)",
        text,
        re.IGNORECASE,
    )
    if not first:
        raise ValueError(f"{generated}: first generated relation not found")
    relations = [f"{first.group(1)} {first.group(2)}"]
    predicates: list[str] = []
    join_pattern = re.compile(
        r"\b(?:INNER\s+JOIN|LEFT\s+OUTER\s+JOIN|RIGHT\s+OUTER\s+JOIN|"
        r"FULL\s+OUTER\s+JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:AS\s+)?"
        r"([A-Za-z_][A-Za-z0-9_]*)\s+ON\s+"
        r"([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\s*=\s*"
        r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)",
        re.IGNORECASE,
    )
    for match in join_pattern.finditer(text):
        relations.append(f"{match.group(1)} {match.group(2)}")
        predicates.append(" ".join(match.group(3).split()))
    where_match = re.search(r"\bWHERE\s+(.*?);\s*$", text, re.IGNORECASE | re.DOTALL)
    if len(relations) < 3 or len(predicates) != len(relations) - 1 or not where_match:
        raise ValueError(f"{generated}: incomplete generated seed skeleton")
    return relations, predicates, " ".join(where_match.group(1).split())


def job_seed(query_id: str, *, max_relations: int = 5, offset: int = 0) -> Seed:
    source_location = f"benchmark/imdb_plan_cost/queries/{query_id}.sql"
    source = REPO_ROOT / source_location
    if is_dataless(source):
        relations, ordered_predicates, where = generated_seed_skeleton(
            "job", f"job_{query_id}_skeleton"
        )
        return compact_seed(
            family="job",
            seed_id=f"job_{query_id}_skeleton",
            source_benchmark="JOB",
            source_version="DuckDB-vendored JOB query set",
            source_query=query_id,
            source_location=source_location,
            topology=classify_topology(ordered_predicates),
            semantics=(
                f"A movie-metadata coverage pattern extracted from JOB {query_id}; "
                "the source equality graph is retained while optionality is varied systematically."
            ),
            relations=relations[:max_relations],
            predicates=ordered_predicates[: max_relations - 1],

            offset=offset,
        )
    text = source.read_text(encoding="utf-8")
    from_match = re.search(r"\bFROM\b(.*?)\bWHERE\b", text, re.IGNORECASE | re.DOTALL)
    if not from_match:
        raise ValueError(f"JOB {query_id}: FROM/WHERE block not found")

    relations: list[str] = []
    aliases: list[str] = []
    for item in from_match.group(1).split(","):
        match = re.match(
            r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*$",
            item,
            re.IGNORECASE,
        )
        if not match:
            raise ValueError(f"JOB {query_id}: unsupported relation item: {item!r}")
        table, alias = match.groups()
        relations.append(f"{table} {alias}")
        aliases.append(alias)

    equality_predicates = re.findall(
        r"\b([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\s*=\s*"
        r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)",
        text,
    )
    edges: list[tuple[str, str, str]] = []
    for predicate in equality_predicates:
        left, right = predicate_aliases(predicate)
        if left in aliases and right in aliases:
            edges.append((left, right, " ".join(predicate.split())))

    included = [aliases[0]]
    ordered_relations = [relations[0]]
    ordered_predicates: list[str] = []
    while len(ordered_relations) < min(max_relations, len(relations)):
        found = False
        # Retain the source title relation before optional annotation leaves so
        # release-year cohorts use a business attribute already in this graph.
        ordered_candidates = sorted(zip(aliases, relations), key=lambda item: item[1].split()[0] != "title")
        for alias, relation in ordered_candidates:
            if alias in included:
                continue
            for left, right, predicate in edges:
                if (left == alias and right in included) or (right == alias and left in included):
                    included.append(alias)
                    ordered_relations.append(relation)
                    ordered_predicates.append(predicate)
                    found = True
                    break
            if found:
                break
        if not found:
            break
    if len(ordered_relations) < 3:
        raise ValueError(f"JOB {query_id}: could not extract a connected three-relation skeleton")

    return compact_seed(
        family="job",
        seed_id=f"job_{query_id}_skeleton",
        source_benchmark="JOB",
        source_version="DuckDB-vendored JOB query set",
        source_query=query_id,
        source_location=source_location,
        topology=classify_topology(ordered_predicates),
        semantics=(
            f"A movie-metadata coverage pattern extracted from JOB {query_id}; "
            "the source equality graph is retained while optionality is varied systematically."
        ),
        relations=ordered_relations,
        predicates=ordered_predicates,

        offset=offset,
    )


def sqlstorm_seed(
    dataset: str,
    query_id: str,
    *,
    offset: int = 0,
) -> Seed:
    source_location = f"auto_test/outerjoin_benchmark/sources/sqlstorm/{dataset}/{query_id}.sql"
    source = REPO_ROOT / source_location
    if is_dataless(source):
        relations, predicates, _ = generated_seed_skeleton(
            dataset, f"sqlstorm_{dataset}_{query_id}"
        )
        return compact_seed(
            family=dataset,
            seed_id=f"sqlstorm_{dataset}_{query_id}",
            source_benchmark="SQLStorm",
            source_version=f"v1.0@{SQLSTORM_COMMIT}",
            source_query=f"v1.0/{dataset}/queries/{query_id}.sql",
            source_location=source_location,
            topology=classify_topology(predicates),
            semantics=(
                f"A SQLStorm {dataset} query pattern whose source relation graph is retained; "
                "a business cohort is enriched under controlled preservation semantics."
            ),
            relations=relations,
            predicates=predicates,

            offset=offset,
        )
    text = source.read_text(encoding="utf-8")
    first = re.search(
        r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
        text,
        re.IGNORECASE,
    )
    if not first:
        raise ValueError(f"SQLStorm {dataset}/{query_id}: first relation not found")
    relations = [f"{first.group(1)} {first.group(2)}"]
    predicates: list[str] = []
    join_pattern = re.compile(
        r"\bJOIN\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*)"
        r"\s+ON\s+(.*?)(?=\bJOIN\b|\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|;)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in join_pattern.finditer(text):
        relations.append(f"{match.group(1)} {match.group(2)}")
        predicates.append(" ".join(match.group(3).split()))
    if len(relations) < 3 or len(predicates) != len(relations) - 1:
        raise ValueError(f"SQLStorm {dataset}/{query_id}: unsupported explicit join skeleton")

    return compact_seed(
        family=dataset,
        seed_id=f"sqlstorm_{dataset}_{query_id}",
        source_benchmark="SQLStorm",
        source_version=f"v1.0@{SQLSTORM_COMMIT}",
        source_query=f"v1.0/{dataset}/queries/{query_id}.sql",
        source_location=source_location,
        topology=classify_topology(predicates),
        semantics=(
            f"A SQLStorm {dataset} query pattern whose source relation graph is retained; "
            "a business cohort is enriched under controlled preservation semantics."
        ),
        relations=relations,
        predicates=predicates,

        offset=offset,
    )


SEEDS: tuple[Seed, ...] = (
    Seed(
        family="tpch",
        seed_id="tpch_q05_region_sales",
        source_benchmark="TPC-H",
        source_version="DuckDB-vendored TPC-H query template",
        source_query="Q5",
        source_location="extension/tpch/dbgen/queries/q05.sql",
        source_hash="495def7debb02ab1def31da07fbc88b4796813b754832ce15d54a35dcb104577",
        topology="chain",
        semantics=(
            "Regional sales in the source date window: retain region-filtered "
            "coverage while exposing missing line-item information."
        ),
        relations=("region r", "nation n", "customer c", "orders o", "lineitem l"),
        predicates=(
            "r.r_regionkey = n.n_regionkey",
            "n.n_nationkey = c.c_nationkey",
            "c.c_custkey = o.o_custkey",
            "o.o_orderkey = l.l_orderkey",
        ),
        projection=(
            "r.r_name, n.n_name, c.c_custkey, o.o_orderkey, "
            "l.l_linenumber, l.l_extendedprice"
        ),

        semantic_vector=("I", "L", "L", "L"),
    ),
    Seed(
        family="tpch",
        seed_id="tpch_q09_supply_chain",
        source_benchmark="TPC-H",
        source_version="DuckDB-vendored TPC-H query template",
        source_query="Q9",
        source_location="extension/tpch/dbgen/queries/q09.sql",
        source_hash="af90ccbe30ece396209e6627c10c0086ed54208100357922ee404de8bb867e56",
        topology="star",
        semantics=(
            "Part supply coverage: retain selected parts while exposing missing "
            "line-item, supplier, supply-record, and order information."
        ),
        relations=("part p", "lineitem l", "supplier s", "partsupp ps", "orders o"),
        predicates=(
            "p.p_partkey = l.l_partkey",
            "l.l_suppkey = s.s_suppkey",
            "ps.ps_suppkey = l.l_suppkey AND ps.ps_partkey = l.l_partkey",
            "o.o_orderkey = l.l_orderkey",
        ),
        projection=(
            "p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, "
            "ps.ps_supplycost, o.o_orderdate"
        ),

        semantic_vector=("L", "L", "F", "L"),
    ),
    Seed(
        family="tpcds",
        seed_id="tpcds_q40_catalog_returns",
        source_benchmark="TPC-DS",
        source_version="DuckDB-vendored TPC-DS query template",
        source_query="Q40",
        source_location="extension/tpcds/dsdgen/queries/40.sql",
        source_hash="d30c0576b8e7de9b43f26f1fbd92381ed9eacbb2c0ad7ed343d651afba552fe1",
        topology="star",
        semantics=(
            "Catalog return attribution: every qualifying catalog sale remains "
            "visible even when no matching return exists; dimensions enrich it."
        ),
        relations=(
            "catalog_sales cs",
            "catalog_returns cr",
            "warehouse w",
            "item i",
            "date_dim d",
        ),
        predicates=(
            "cs.cs_order_number = cr.cr_order_number AND cs.cs_item_sk = cr.cr_item_sk",
            "cs.cs_warehouse_sk = w.w_warehouse_sk",
            "cs.cs_item_sk = i.i_item_sk AND i.i_current_price BETWEEN 0.99 AND 1.49",
            "cs.cs_sold_date_sk = d.d_date_sk "
            "AND d.d_date BETWEEN DATE '2000-02-10' AND DATE '2000-04-10'",
        ),
        projection=(
            "cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, "
            "w.w_state, i.i_item_id, d.d_date"
        ),

        semantic_vector=("L", "I", "I", "I"),
    ),
    Seed(
        family="tpcds",
        seed_id="tpcds_q72_fulfillment",
        source_benchmark="TPC-DS",
        source_version="DuckDB-vendored TPC-DS query template",
        source_query="Q72",
        source_location="extension/tpcds/dsdgen/queries/72.sql",
        source_hash="8646866ad7d1ba9e888b70c7f5ccf6480f8085475381b8ca747c85c0c409a744",
        topology="branch",
        semantics=(
            "Catalog fulfillment coverage: sales are matched with inventory, "
            "warehouse, item, and optional promotion information."
        ),
        relations=("catalog_sales cs", "inventory inv", "warehouse w", "item i", "promotion p"),
        predicates=(
            "cs.cs_item_sk = inv.inv_item_sk AND cs.cs_quantity > inv.inv_quantity_on_hand",
            "inv.inv_warehouse_sk = w.w_warehouse_sk",
            "cs.cs_item_sk = i.i_item_sk",
            "cs.cs_promo_sk = p.p_promo_sk",
        ),
        projection=(
            "cs.cs_order_number, cs.cs_item_sk, inv.inv_quantity_on_hand, "
            "w.w_warehouse_name, i.i_item_id, p.p_promo_name"
        ),

        semantic_vector=("I", "I", "I", "L"),
    ),
    Seed(
        family="job",
        seed_id="job_10a_cast_credits",
        source_benchmark="JOB",
        source_version="DuckDB-vendored JOB query set",
        source_query="10a",
        source_location="benchmark/imdb_plan_cost/queries/10a.sql",
        source_hash="dcffd7d004228d834af7bf332e365837cc5a3fb60fb3859a55235da6d1455a89",
        topology="chain",
        semantics=(
            "Movie-credit coverage: qualifying titles retain cast records while "
            "role and company annotations may be absent."
        ),
        relations=("title t", "cast_info ci", "role_type rt", "movie_companies mc", "company_name cn"),
        predicates=(
            "t.id = ci.movie_id",
            "rt.id = ci.role_id",
            "t.id = mc.movie_id",
            "cn.id = mc.company_id",
        ),
        projection=(
            "t.id AS title_id, t.title, ci.person_id, cn.name AS company_name, "
            "rt.role, mc.company_id"
        ),

        semantic_vector=("I", "L", "I", "L"),
    ),
    Seed(
        family="job",
        seed_id="job_17a_movie_annotations",
        source_benchmark="JOB",
        source_version="DuckDB-vendored JOB query set",
        source_query="17a",
        source_location="benchmark/imdb_plan_cost/queries/17a.sql",
        source_hash="a52d479958ec18149f197df005f183f8cee35712398524f344b9751c9dce9fe2",
        topology="chain",
        semantics=(
            "Movie annotation coverage: title/cast/name records form the backbone, "
            "while keyword and company annotations are optional."
        ),
        relations=("title t", "cast_info ci", "name n", "movie_keyword mk", "keyword k"),
        predicates=(
            "t.id = ci.movie_id",
            "ci.person_id = n.id AND n.name LIKE 'B%'",
            "t.id = mk.movie_id",
            "mk.keyword_id = k.id",
        ),
        projection=(
            "t.id AS title_id, t.title, n.id AS person_id, n.name, "
            "mk.keyword_id, k.keyword"
        ),

        semantic_vector=("I", "I", "L", "L"),
    ),
    Seed(
        family="tpch",
        seed_id="sqlstorm_tpch_19222",
        source_benchmark="SQLStorm",
        source_version=f"v1.0@{SQLSTORM_COMMIT}",
        source_query="v1.0/tpch/queries/19222.sql",
        source_location="auto_test/outerjoin_benchmark/sources/sqlstorm/tpch/19222.sql",
        source_hash="e15dda85b9d7641d92af003cee11263536477bec48d46f9ceb773f19bdeeaed5",
        topology="chain",
        semantics=(
            "Part-supplier coverage adapted from SQLStorm: selected parts remain "
            "visible when a supply or supplier record is missing."
        ),
        relations=("part p", "partsupp ps", "supplier s"),
        predicates=("p.p_partkey = ps.ps_partkey", "ps.ps_suppkey = s.s_suppkey"),
        projection="p.p_name, s.s_name, ps.ps_availqty",

        semantic_vector=("L", "F"),
    ),
    Seed(
        family="tpcds",
        seed_id="sqlstorm_tpcds_10809",
        source_benchmark="SQLStorm",
        source_version=f"v1.0@{SQLSTORM_COMMIT}",
        source_query="v1.0/tpcds/queries/10809.sql",
        source_location="auto_test/outerjoin_benchmark/sources/sqlstorm/tpcds/10809.sql",
        source_hash="a56c40177d28377c0be71322edce5973456095cbd730eb18f5f82460690090db",
        topology="branch",
        semantics=(
            "Customer shopping-context coverage adapted from SQLStorm: customer "
            "address, sale date, and sale time are modeled as optional context."
        ),
        relations=("customer c", "customer_address ca", "store_sales ss", "date_dim d", "time_dim t"),
        predicates=(
            "c.c_current_addr_sk = ca.ca_address_sk AND ca.ca_state = 'CA'",
            "c.c_customer_sk = ss.ss_customer_sk",
            "ss.ss_sold_date_sk = d.d_date_sk AND d.d_year = 2023",
            "ss.ss_sold_time_sk = t.t_time_sk",
        ),
        projection=(
            "c.c_customer_id, ca.ca_city, ss.ss_ticket_number, ss.ss_quantity, "
            "d.d_date, t.t_hour"
        ),

        semantic_vector=("L", "I", "F", "R"),
    ),
    Seed(
        family="job",
        seed_id="sqlstorm_job_15596",
        source_benchmark="SQLStorm",
        source_version=f"v1.0@{SQLSTORM_COMMIT}",
        source_query="v1.0/job/queries/15596.sql",
        source_location="auto_test/outerjoin_benchmark/sources/sqlstorm/job/15596.sql",
        source_hash="f5d4cd1e5c846800351c12a8953bb5b72e9e0526c8a9c005e8234b31a80830de",
        topology="star",
        semantics=(
            "Cast-credit coverage adapted from SQLStorm: a selected cast record "
            "is retained even when alternate-name or role metadata is absent."
        ),
        relations=("cast_info ci", "aka_name a", "title t", "role_type r"),
        predicates=(
            "ci.person_id = a.person_id",
            "ci.movie_id = t.id",
            "ci.role_id = r.id",
        ),
        projection=(
            "ci.id AS cast_id, a.name AS actor_name, t.title AS movie_title, "
            "ci.nr_order, r.role"
        ),

        semantic_vector=("L", "I", "L"),
    ),
)


ADDITIONAL_SEEDS: tuple[Seed, ...] = (
    compact_seed(
        family="tpch",
        seed_id="tpch_q03_order_revenue",
        source_benchmark="TPC-H",
        source_version="DuckDB-vendored TPC-H query template",
        source_query="Q3",
        source_location="extension/tpch/dbgen/queries/q03.sql",
        topology="chain",
        semantics="Customer orders are the mandatory backbone and line items provide optional revenue detail.",
        relations=("customer c", "orders o", "lineitem l"),
        predicates=("c.c_custkey = o.o_custkey", "o.o_orderkey = l.l_orderkey"),

        offset=0,
    ),
    compact_seed(
        family="tpch",
        seed_id="tpch_q07_trade_flow",
        source_benchmark="TPC-H",
        source_version="DuckDB-vendored TPC-H query template",
        source_query="Q7",
        source_location="extension/tpch/dbgen/queries/q07.sql",
        topology="chain",
        semantics="Supplier-to-customer trade flow with optional order and nation annotations.",
        relations=("supplier s", "lineitem l", "orders o", "customer c", "nation n"),
        predicates=(
            "s.s_suppkey = l.l_suppkey",
            "l.l_orderkey = o.o_orderkey",
            "o.o_custkey = c.c_custkey",
            "s.s_nationkey = n.n_nationkey",
        ),

        offset=1,
    ),
    compact_seed(
        family="tpch",
        seed_id="tpch_q08_market_share",
        source_benchmark="TPC-H",
        source_version="DuckDB-vendored TPC-H query template",
        source_query="Q8",
        source_location="extension/tpch/dbgen/queries/q08.sql",
        topology="chain",
        semantics="Part-to-region market coverage through line items, orders, customers, and geography.",
        relations=("part p", "lineitem l", "orders o", "customer c", "nation n", "region r"),
        predicates=(
            "p.p_partkey = l.l_partkey",
            "l.l_orderkey = o.o_orderkey",
            "o.o_custkey = c.c_custkey",
            "c.c_nationkey = n.n_nationkey",
            "n.n_regionkey = r.r_regionkey",
        ),

        offset=2,
    ),
    compact_seed(
        family="tpcds",
        seed_id="tpcds_q05_web_channel",
        source_benchmark="TPC-DS",
        source_version="DuckDB-vendored TPC-DS query template",
        source_query="Q5",
        source_location="extension/tpcds/dsdgen/queries/05.sql",
        topology="star",
        semantics="Web returns are reconciled with sales and enriched with date and site context.",
        relations=("web_returns wr", "web_sales ws", "date_dim d", "web_site web"),
        predicates=(
            "wr.wr_item_sk = ws.ws_item_sk AND wr.wr_order_number = ws.ws_order_number",
            "ws.ws_sold_date_sk = d.d_date_sk",
            "ws.ws_web_site_sk = web.web_site_sk",
        ),

        offset=0,
    ),
    compact_seed(
        family="tpcds",
        seed_id="tpcds_q80_store_channel",
        source_benchmark="TPC-DS",
        source_version="DuckDB-vendored TPC-DS query template",
        source_query="Q80",
        source_location="extension/tpcds/dsdgen/queries/80.sql",
        topology="star",
        semantics="Store sales retain optional return records and date, store, and item annotations.",
        relations=("store_sales ss", "store_returns sr", "date_dim d", "store s", "item i"),
        predicates=(
            "ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number",
            "ss.ss_sold_date_sk = d.d_date_sk",
            "ss.ss_store_sk = s.s_store_sk",
            "ss.ss_item_sk = i.i_item_sk",
        ),

        offset=1,
    ),
    compact_seed(
        family="tpcds",
        seed_id="tpcds_q93_return_reason",
        source_benchmark="TPC-DS",
        source_version="DuckDB-vendored TPC-DS query template",
        source_query="Q93",
        source_location="extension/tpcds/dsdgen/queries/93.sql",
        topology="chain",
        semantics="Store-sale records are associated with optional returns and their reason dimension.",
        relations=("store_sales ss", "store_returns sr", "reason r"),
        predicates=(
            "ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number",
            "sr.sr_reason_sk = r.r_reason_sk",
        ),

        offset=2,
    ),
    compact_seed(
        family="tpcds",
        seed_id="tpcds_q51_channel_balance",
        source_benchmark="TPC-DS",
        source_version="DuckDB-vendored TPC-DS query template",
        source_query="Q51",
        source_location="extension/tpcds/dsdgen/queries/51.sql",
        topology="chain",
        semantics="Web and store sales streams are reconciled by item and date coverage.",
        relations=("web_sales ws", "date_dim d", "store_sales ss"),
        predicates=(
            "ws.ws_sold_date_sk = d.d_date_sk",
            "ws.ws_item_sk = ss.ss_item_sk AND ws.ws_sold_date_sk = ss.ss_sold_date_sk",
        ),

        offset=3,
    ),
    compact_seed(
        family="tpcds",
        seed_id="tpcds_q97_customer_item_overlap",
        source_benchmark="TPC-DS",
        source_version="DuckDB-vendored TPC-DS query template",
        source_query="Q97",
        source_location="extension/tpcds/dsdgen/queries/97.sql",
        topology="chain",
        semantics="Store and catalog activity is reconciled for the same customer-item pair.",
        relations=("store_sales ss", "date_dim d", "catalog_sales cs"),
        predicates=(
            "ss.ss_sold_date_sk = d.d_date_sk",
            "ss.ss_customer_sk = cs.cs_bill_customer_sk AND ss.ss_item_sk = cs.cs_item_sk",
        ),

        offset=0,
    ),
    job_seed("01a", offset=0),
    job_seed("06a", offset=1),
    job_seed("11a", offset=2),
    job_seed("16a", offset=3),
    job_seed("20a", offset=0),
    job_seed("21a", offset=1),
    job_seed("26a", offset=2),
    job_seed("30a", offset=3),
    sqlstorm_seed(
        "tpch", "17751",
        offset=1,
    ),
    sqlstorm_seed(
        "tpch", "25509",
        offset=2,
    ),
    sqlstorm_seed(
        "tpch", "15031",
        offset=3,
    ),
    sqlstorm_seed(
        "tpcds", "11376",
        offset=1,
    ),
    sqlstorm_seed(
        "tpcds", "28643",
        offset=2,
    ),
    sqlstorm_seed(
        "tpcds", "14368",
        offset=3,
    ),
    sqlstorm_seed(
        "job", "11914",
        offset=1,
    ),
    sqlstorm_seed(
        "job", "18930",
        offset=2,
    ),
    sqlstorm_seed(
        "job", "13193",
        offset=3,
    ),
)

SEEDS = SEEDS + ADDITIONAL_SEEDS


def relation_alias(relation: str) -> str:
    return relation.split()[-1]


def active_edge_predicate(predicate: str) -> str:
    """Retain the source equality, including its actual foreign-key column."""
    match = SIMPLE_EDGE_EQUALITY.search(predicate)
    if not match:
        raise ValueError(f"join edge has no plain qualified equality: {predicate}")
    return match.group(0)


def sql_join_graph(sql: str) -> Counter[tuple[str, str]]:
    """Extract the undirected alias pairs used by generated ON equalities."""
    graph: Counter[tuple[str, str]] = Counter()
    pattern = re.compile(r"\bON\s+" + SIMPLE_EDGE_EQUALITY.pattern, re.IGNORECASE)
    for match in pattern.finditer(sql):
        left_alias = match.group(1).split(".", 1)[0]
        right_alias = match.group(2).split(".", 1)[0]
        graph[tuple(sorted((left_alias, right_alias)))] += 1
    return graph


def bushy_root_partition(seed: Seed) -> tuple[set[str], set[str], int] | None:
    """Return the most balanced connected root partition, if it is truly bushy."""
    aliases = [relation_alias(relation) for relation in seed.relations]
    alias_order = {alias: index for index, alias in enumerate(aliases)}
    edges = [(*predicate_aliases(predicate), index) for index, predicate in enumerate(seed.predicates)]

    def component(start: str, excluded_edge: int) -> set[str]:
        visited = {start}
        pending = [start]
        while pending:
            current = pending.pop()
            for left, right, edge_index in edges:
                if edge_index == excluded_edge:
                    continue
                if left == current and right not in visited:
                    visited.add(right)
                    pending.append(right)
                elif right == current and left not in visited:
                    visited.add(left)
                    pending.append(left)
        return visited

    candidates: list[tuple[int, int, set[str], set[str]]] = []
    all_aliases = set(aliases)
    for left, right, edge_index in edges:
        left_side = component(left, edge_index)
        right_side = all_aliases - left_side
        if right not in right_side:
            raise ValueError(f"{seed.seed_id}: source skeleton is not an acyclic connected graph")
        candidates.append((abs(len(left_side) - len(right_side)), edge_index, left_side, right_side))

    _, edge_index, first, second = min(candidates, key=lambda item: (item[0], item[1]))
    if min(len(first), len(second)) < 2:
        return None
    if min(alias_order[alias] for alias in first) > min(alias_order[alias] for alias in second):
        first, second = second, first
    return first, second, edge_index


def selectivity_anchor(seed: Seed) -> str:
    """Choose a deterministic, usually high-cardinality central join key."""
    aliases = [relation_alias(relation) for relation in seed.relations]
    alias_order = {alias: index for index, alias in enumerate(aliases)}
    degrees: Counter[str] = Counter()
    columns: dict[str, list[str]] = {alias: [] for alias in aliases}
    for predicate in seed.predicates:
        match = SIMPLE_EDGE_EQUALITY.search(active_edge_predicate(predicate))
        if not match:
            raise ValueError(f"{seed.seed_id}: no equality column for selectivity anchor")
        for reference in match.groups():
            alias = reference.split(".", 1)[0]
            degrees[alias] += 1
            columns.setdefault(alias, []).append(reference)
    anchor_alias = max(aliases, key=lambda alias: (degrees[alias], alias_order[alias]))
    frequency = Counter(columns[anchor_alias])
    first_seen = {column: index for index, column in enumerate(columns[anchor_alias])}
    return max(frequency, key=lambda column: (frequency[column], -first_seen[column]))


SELECT_LIST_PATTERN = re.compile(
    r"^SELECT\s+.*?^FROM\s+", re.IGNORECASE | re.MULTILINE | re.DOTALL
)


def add_v3_aggregation(sql: str, seed: Seed, aggregate_variant: str) -> tuple[str, str]:
    """Replace only the output list with a deterministic root aggregation."""
    anchor = selectivity_anchor(seed)
    group_key = next(
        reference
        for predicate in seed.predicates
        for reference in SIMPLE_EDGE_EQUALITY.search(active_edge_predicate(predicate)).groups()
        if reference != anchor
    )
    if aggregate_variant == "global_count":
        projection = "COUNT(*) AS row_count"
        group_by = ""
    elif aggregate_variant == "grouped_min":
        projection = f"{group_key} AS group_key, MIN({anchor}) AS min_key"
        group_by = f"\nGROUP BY {group_key}"
    elif aggregate_variant == "grouped_max":
        projection = f"{group_key} AS group_key, MAX({anchor}) AS max_key"
        group_by = f"\nGROUP BY {group_key}"
    elif aggregate_variant == "grouped_sum":
        projection = f"{group_key} AS group_key, SUM({anchor}) AS key_sum"
        group_by = f"\nGROUP BY {group_key}"
    else:
        raise ValueError(f"unknown v3 aggregate variant: {aggregate_variant}")

    aggregated, replacements = SELECT_LIST_PATTERN.subn(
        f"SELECT {projection}\nFROM ", sql, count=1
    )
    if replacements != 1:
        raise ValueError(f"{seed.seed_id}: generated SQL has an unexpected SELECT/FROM shape")
    aggregated = aggregated.rstrip()
    if not aggregated.endswith(";"):
        raise ValueError(f"{seed.seed_id}: generated SQL must end with a semicolon")
    aggregated = aggregated[:-1] + group_by + ";\n"
    metadata = (
        "-- corpus_version: v3\n"
        "-- workload_role: source-derived aggregation coverage; no timing-based selection\n"
        f"-- aggregate_variant: {aggregate_variant}; anchor={anchor}; group_key={group_key}\n"
    )
    return aggregated.replace("SELECT ", metadata + "SELECT ", 1), anchor


def verify_source(seed: Seed) -> None:
    if seed.source_location.startswith(("http://", "https://")):
        # Remote artifacts are pinned by immutable URL and recorded hash.  The
        # generator intentionally remains usable without network access.
        return
    source = REPO_ROOT / seed.source_location
    if not source.is_file():
        raise FileNotFoundError(f"{seed.seed_id}: source query not found: {source}")
    if is_dataless(source):
        # compact_seed already recovered the checked-in hash for this exact
        # source location. Avoid triggering an unbounded iCloud download.
        return
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != seed.source_hash:
        raise RuntimeError(
            f"{seed.seed_id}: source hash changed: expected {seed.source_hash}, got {actual}"
        )


def sql_join_kind_counts(sql: str) -> Counter[str]:
    """Count emitted I/L/R/F labels while ignoring full-line SQL comments."""
    statement = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    counts: Counter[str] = Counter()
    for match in JOIN_KEYWORD_PATTERN.finditer(statement):
        keyword = match.group(0).upper()
        if keyword.startswith("INNER"):
            counts["I"] += 1
        elif keyword.startswith("LEFT"):
            counts["L"] += 1
        elif keyword.startswith("RIGHT"):
            counts["R"] += 1
        else:
            counts["F"] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", help=argparse.SUPPRESS)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--batch", type=int, default=0, help="Disjoint candidate batch (default: 0)")
    parser.add_argument("--per-family", type=int, default=180)
    parser.add_argument("--core-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.version or args.core_only:
        parser.error("Versioned generation is retired; run without --version/--core-only for the unique corpus")
    from balanced_benchmark import generate
    generate(args.root or DEFAULT_ROOT, args.per_family, args.batch)


if __name__ == "__main__":
    main()
