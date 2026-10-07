#!/usr/bin/env python3
"""Generate the provenance-backed OuterJoin benchmark corpus.

The generated workloads are independent of OuterYan performance results.  Each seed
records an upstream benchmark query and retains a connected subgraph of its
relation instances and join predicates.  The SQL is normalized to a flat
projection/filter/join skeleton so that it remains inside the optimizer's
current applicability envelope. V3 deliberately replaces only that projection
with a root aggregation while preserving the same source graph.

The active ``benchmark`` corpus contains each SQL identity once, across join, graph and aggregate queries.
Query names describe type, execution family, source/structure, join kinds and filter band.
Historical suite names are retained only in aliases and archived definitions.
The internal versioned builders are deterministic source-expansion stages; their
intermediate SQL is created in a temporary directory, never an active workload.

"""

from __future__ import annotations

import argparse
import csv
import datetime as datetime_module
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from benchmark_corpus import ARCHIVE_NAME, canonical_query_id, read_manifest, sql_fingerprint
from database_paths import database_path

from legacy_corpus import (
    COMPLETED_QUERY_PATHS,
    LEGACY_OUTERYAN_WINS,
    LEGACY_QUERIES,
    REFERENCE_RUN,
    TIMEOUT_QUERY_PATHS,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_ROOT = SCRIPT_DIR / "outerjoin_benchmark"
DEFAULT_V2_ROOT = DEFAULT_ROOT / "v2"
DEFAULT_V3_ROOT = DEFAULT_ROOT / "v3"
LEGACY_ROOT = SCRIPT_DIR / "outerjoin_query_old"
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
V2_JOB_REGRESSIONS: tuple[tuple[str, str, str], ...] = (
    ("ojb_sqlstorm_job_11914_bdmx", "1af32617cb10164c5f999a0f99f196b23232059a40dd8f0f2ff5e1eb81af7836", "0.772"),
    ("oy_jb_jb_bushy4a_v2", "6dca40cd9267b67ea297a5245c6cd0d9b0fe7bf8653d1d6c6a643f89e9a82103", "0.857"),
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


def copy_filter_metadata(row: dict[str, str]) -> dict[str, str]:
    return {key: row[key] for key in (
        "filter_design_revision", "selectivity_tier", "semantic_tier", "target_fraction",
        "target_min_fraction", "target_max_fraction", "selectivity_profile", "selectivity_anchor",
        "target_min_inclusive", "target_max_inclusive", "source_filter_adaptation",
        "selectivity_predicate", "filter_semantics", "selectivity_denominator", "calibration_rows",
        "calibration_qualified_rows", "calibration_fraction", "calibration_in_range",
        "selectivity_scope", "parameter_policy",
    )}


def semantic_comment(metadata: dict[str, str]) -> str:
    return (f"-- semantic_filter: {metadata['selectivity_profile']}; "
            f"tier={metadata['semantic_tier']}; {metadata['filter_semantics']}\n"
            f"-- predicate: {metadata['selectivity_predicate']}\n"
            "-- selectivity_scope: base-entity calibration; not a joined-output percentage\n")


def replace_where(sql: str, predicate: str) -> str:
    result, count = re.subn(r"\bWHERE\s+.*?(?=\s+GROUP\s+BY\b|;)",
                            lambda _: f"WHERE {predicate}", sql, count=1,
                            flags=re.IGNORECASE | re.DOTALL)
    if count != 1:
        raise ValueError("Expected one outer WHERE clause when replacing the semantic cohort")
    return result


def active_query_id(prefix: str, row: dict[str, str]) -> str:
    base = row["query_id"]
    if row["family"] == "graph":
        instance = GRAPH_CONTROL_FILENAMES.index(f"{base}.sql") + 1
        base = re.sub(r"_s\d+$", "", base) + f"_case{instance:02d}_" + row["selectivity_tier"]
    return f"{prefix}__sem__{base}"


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


def control_filter_metadata(sql: str, family: str, index: int) -> dict[str, str]:
    statement = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    relations = re.findall(
        r"\b(?:FROM|JOIN)\s*\(*\s*(\w+)(?:\s+(?:AS\s+)?"
        r"(?!ON\b|LEFT\b|RIGHT\b|FULL\b|INNER\b|JOIN\b|WHERE\b)([A-Za-z_]\w*))?",
        statement, re.IGNORECASE,
    )
    tables = {table.lower(): alias or table for table, alias in relations}
    options = {
        "tpch": (("orders", "tpch_order_date", "o_orderdate"),
                 ("partsupp", "tpch_supply_cost", "ps_supplycost"),
                 ("supplier", "tpch_supplier_balance", "s_acctbal"),
                 ("customer", "tpch_customer_balance", "c_acctbal")),
        "tpcds": tuple((f"{channel}_sales", f"tpcds_{channel}_quantity", f"{prefix}_quantity")
                       for channel, prefix in (("store", "ss"), ("web", "ws"), ("catalog", "cs"))),
        "job": (("title", "job_release_year", "production_year"),),
        "graph": (("r1", "graph_source_range", "src"),),
    }[family]
    for table, profile, column in options:
        if table in tables:
            available = [name for name in SEMANTIC_TIERS
                         if semantic_metadata(profile, column, name)["calibration_in_range"] == "true"]
            tier = available[index % len(available)]
            return semantic_metadata(profile, f"{tables[table]}.{column}", tier)
    raise ValueError(f"No semantic business attribute in {family} control: {tables}")

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


def build_left_deep(seed: Seed, kinds: Sequence[str]) -> str:
    expression = seed.relations[0]
    for relation, predicate, kind in zip(seed.relations[1:], seed.predicates, kinds):
        predicate = active_edge_predicate(predicate)
        expression = f"({expression} {JOIN_SQL[kind]} {relation} ON {predicate})"
    return expression


def flip_join_kind(kind: str) -> str:
    return {"I": "I", "L": "R", "R": "L", "F": "F"}[kind]


def build_right_deep(seed: Seed, kinds: Sequence[str]) -> str:
    """Build a right-deep tree whose emitted operators are given by kinds."""
    expression = seed.relations[0]
    for relation, predicate, kind in zip(seed.relations[1:], seed.predicates, kinds):
        predicate = active_edge_predicate(predicate)
        expression = f"({relation} {JOIN_SQL[kind]} {expression} ON {predicate})"
    return expression


def build_right_mirror(seed: Seed, kinds: Sequence[str]) -> str:
    """Mirror a labeled left-deep tree into an equivalent right-deep tree."""
    return build_right_deep(seed, tuple(flip_join_kind(kind) for kind in kinds))


def build_alternate_deep(
    seed: Seed,
    kinds: Sequence[str] | None = None,
    *,
    right_deep: bool,
) -> str:
    """Build a second cross-product-free deep traversal from the last relation."""
    return build_connected_deep(
        seed,
        kinds=kinds,
        right_deep=right_deep,
        start_index=len(seed.relations) - 1,
        prefer_max_edge=True,
    )


def build_connected_deep(
    seed: Seed,
    *,
    kinds: Sequence[str] | None = None,
    right_deep: bool,
    start_index: int,
    prefer_max_edge: bool,
) -> str:
    """Build a connected labeled traversal from a selected relation."""
    edge_kinds = tuple(kinds or ("F",) * len(seed.predicates))
    if len(edge_kinds) != len(seed.predicates):
        raise ValueError(f"{seed.seed_id}: join-vector length mismatch")
    aliases = [relation_alias(relation) for relation in seed.relations]
    relation_by_alias = dict(zip(aliases, seed.relations))
    edges = [(*predicate_aliases(predicate), index) for index, predicate in enumerate(seed.predicates)]
    start_alias = aliases[start_index]
    visited = {start_alias}
    expression = relation_by_alias[start_alias]
    while len(visited) < len(aliases):
        candidates: list[tuple[int, str]] = []
        for left, right, edge_index in edges:
            if (left in visited) == (right in visited):
                continue
            candidates.append((edge_index, right if left in visited else left))
        if not candidates:
            raise ValueError(f"{seed.seed_id}: cannot form alternate deep traversal")
        edge_index, new_alias = (max(candidates) if prefer_max_edge else min(candidates))
        relation = relation_by_alias[new_alias]
        predicate = active_edge_predicate(seed.predicates[edge_index])
        if right_deep:
            expression = (
                f"({relation} {JOIN_SQL[edge_kinds[edge_index]]} "
                f"{expression} ON {predicate})"
            )
        else:
            expression = (
                f"({expression} {JOIN_SQL[edge_kinds[edge_index]]} "
                f"{relation} ON {predicate})"
            )
        visited.add(new_alias)
    return expression


def build_secondary_right_deep(
    seed: Seed, kinds: Sequence[str] | None = None
) -> str:
    """Build a third syntactically distinct connected right-deep tree."""
    edge_kinds = tuple(kinds or ("F",) * len(seed.predicates))
    existing = {
        build_right_deep(seed, edge_kinds),
        build_alternate_deep(seed, edge_kinds, right_deep=True),
    }
    middle = len(seed.relations) // 2
    start_order = [middle, *range(len(seed.relations))]
    for start_index in dict.fromkeys(start_order):
        for prefer_max_edge in (False, True):
            candidate = build_connected_deep(
                seed,
                kinds=edge_kinds,
                right_deep=True,
                start_index=start_index,
                prefer_max_edge=prefer_max_edge,
            )
            if candidate not in existing:
                return candidate
    raise ValueError(f"{seed.seed_id}: cannot form a distinct secondary right-deep traversal")


def alternate_vector(seed: Seed) -> tuple[str, ...]:
    """Return a second deterministic mixture without consulting measurements."""
    edge_count = len(seed.predicates)
    offset = sum(seed.seed_id.encode("utf-8")) % len(JOIN_SQL)
    candidate = mixed_vector(edge_count, offset)
    if candidate == seed.semantic_vector:
        candidate = mixed_vector(edge_count, offset + 1)
    return candidate


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


def normalize_active_sql(sql: str, *, flatten_aggregate: bool = False) -> str:
    """Keep the join graph/grouping while forcing the active applicability envelope."""
    normalized = re.sub(
        r"\b(?:INNER|LEFT(?:\s+OUTER)?|RIGHT(?:\s+OUTER)?|FULL(?:\s+OUTER)?)\s+JOIN\b",
        ACTIVE_JOIN_SQL,
        sql,
        flags=re.IGNORECASE,
    )
    if flatten_aggregate:
        normalized, select_count = re.subn(
            r"\ASELECT\b.*?\bFROM\b",
            "SELECT *\nFROM",
            normalized,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if select_count != 1:
            raise ValueError("could not flatten active aggregate projection")
        normalized, group_count = re.subn(
            r"\s+GROUP\s+BY\b.*?(?=;)",
            "",
            normalized,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if group_count != 1:
            raise ValueError("could not remove active aggregate GROUP BY")
    return normalized


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


def build_bushy_mixed(seed: Seed, kinds: Sequence[str], *, alternate: bool = False) -> str:
    """Build a balanced connected tree without introducing cross products."""
    aliases = [relation_alias(relation) for relation in seed.relations]
    alias_order = {alias: index for index, alias in enumerate(aliases)}
    relation_by_alias = dict(zip(aliases, seed.relations))
    edges = [(*predicate_aliases(predicate), index) for index, predicate in enumerate(seed.predicates)]
    all_aliases = set(aliases)

    def split(nodes: set[str]) -> tuple[set[str], set[str], int]:
        candidates: list[tuple[int, int, set[str], set[str]]] = []
        for left, right, edge_index in edges:
            if left not in nodes or right not in nodes:
                continue
            visited = {left}
            pending = [left]
            while pending:
                current = pending.pop()
                for edge_left, edge_right, candidate_index in edges:
                    if candidate_index == edge_index:
                        continue
                    if edge_left not in nodes or edge_right not in nodes:
                        continue
                    if edge_left == current and edge_right not in visited:
                        visited.add(edge_right)
                        pending.append(edge_right)
                    elif edge_right == current and edge_left not in visited:
                        visited.add(edge_left)
                        pending.append(edge_left)
            other = nodes - visited
            if right in other:
                candidates.append((abs(len(visited) - len(other)), edge_index, visited, other))
        if not candidates:
            raise ValueError(f"{seed.seed_id}: cannot form a connected bushy subplan")
        candidates.sort(key=lambda item: (item[0], item[1]))
        choices = candidates
        if nodes == all_aliases:
            choices = [
                candidate
                for candidate in candidates
                if min(len(candidate[2]), len(candidate[3])) >= 2
            ]
            if not choices:
                raise ValueError(f"{seed.seed_id}: source skeleton has no bushy root split")
        candidate_index = 1 if alternate and len(choices) > 1 else 0
        _, edge_index, first, second = choices[candidate_index]
        if min(alias_order[alias] for alias in first) > min(alias_order[alias] for alias in second):
            first, second = second, first
        if alternate and len(choices) == 1:
            first, second = second, first
        return first, second, edge_index

    def build(nodes: set[str]) -> str:
        if len(nodes) == 1:
            return relation_by_alias[next(iter(nodes))]
        left_nodes, right_nodes, edge_index = split(nodes)
        return (
            f"({build(left_nodes)} {JOIN_SQL[kinds[edge_index]]} {build(right_nodes)} "
            f"ON {active_edge_predicate(seed.predicates[edge_index])})"
        )

    if bushy_root_partition(seed) is None:
        raise ValueError(f"{seed.seed_id}: source skeleton has no cross-product-free bushy tree")
    return build(set(aliases))


def query_sql(seed: Seed, expression: str, variant: str, variant_semantics: str) -> str:
    source = f"{seed.source_benchmark} {seed.source_query}"
    return (
        f"-- source: {source}\n"
        f"-- transformation: connected join-subgraph adaptation; {variant_semantics}\n"
        f"-- business_semantics: {seed_filter_metadata(seed)['filter_semantics']}\n"
        f"SELECT {seed.projection}\n"
        f"FROM {expression}\n"
        f"WHERE {seed.where};\n"
    )


def variant_rows(seed: Seed, seed_index: int) -> Iterable[tuple[str, str, str, str, str]]:
    edge_count = len(seed.predicates)
    full_vector = ("F",) * edge_count
    legacy_suffix_kinds = ("L", "R", "F")
    right_suffix_kind = legacy_suffix_kinds[(2 * seed_index + 1) % len(legacy_suffix_kinds)]
    yield (
        "ldmx",
        "".join(full_vector),
        "left_deep",
        "primary left-deep FULL-outer applicability form",
        query_sql(
            seed,
            build_left_deep(seed, full_vector),
            "ldmx",
            "primary left-deep FULL-outer applicability form",
        ),
    )
    yield (
        "rdmx",
        "".join(full_vector),
        "right_deep",
        "right-deep FULL-outer applicability form",
        query_sql(
            seed,
            build_right_mirror(seed, full_vector),
            "rdmx",
            "right-deep FULL-outer applicability form",
        ),
    )
    bushy_eligible = bushy_root_partition(seed) is not None
    if bushy_eligible:
        yield (
            "bmx",
            "".join(full_vector),
            "bushy",
            "balanced connected bushy FULL-outer applicability form",
            query_sql(
                seed,
                build_bushy_mixed(seed, full_vector),
                "bmx",
                "cross-product-free bushy FULL-outer applicability form",
            ),
        )
    else:
        alternate = alternate_vector(seed)
        yield (
            "alt",
            "".join(alternate),
            "left_deep",
            "alternate mixed applicability form",
            query_sql(
                seed,
                build_left_deep(seed, alternate),
                "alt",
                "alternate mixed form; bushy grouping is structurally ineligible",
            ),
        )

    if bushy_eligible:
        primary_bushy = build_bushy_mixed(seed, full_vector)
        alternate_bushy = build_bushy_mixed(seed, full_vector, alternate=True)
        if alternate_bushy == primary_bushy:
            raise ValueError(f"{seed.seed_id}: secondary bushy tree duplicates the primary tree")
        yield (
            "bdmx",
            "".join(full_vector),
            "bushy",
            "secondary connected bushy FULL-outer applicability form",
            query_sql(
                seed,
                alternate_bushy,
                "bdmx",
                "secondary cross-product-free bushy FULL-outer applicability form",
            ),
        )
    else:
        yield (
            "rdax",
            "".join(full_vector),
            "right_deep",
            "secondary right-deep FULL-outer applicability form",
            query_sql(
                seed,
                build_secondary_right_deep(seed),
                "rdax",
                "secondary right-deep FULL-outer applicability form",
            ),
        )
    yield (
        f"rdu{right_suffix_kind}",
        "".join(full_vector),
        "right_deep",
        "secondary right-deep FULL-outer control",
        query_sql(
            seed,
            build_alternate_deep(seed, right_deep=True),
            f"rdu{right_suffix_kind}",
            "secondary right-deep FULL-outer control",
        ),
    )


def balanced_mixed_vector(
    seed_index: int, variant_index: int, edge_count: int
) -> tuple[str, ...]:
    """Assign a mixed vector while balancing I/L/R/F over the whole v2 core."""
    if edge_count < 2:
        raise ValueError("a mixed join vector requires at least two edges")
    prior_edge_slots = sum(
        len(previous.predicates) * 5 for previous in SEEDS[:seed_index]
    )
    offset = (prior_edge_slots + variant_index) % len(MIXED_JOIN_CYCLE)
    return tuple(
        MIXED_JOIN_CYCLE[(offset + edge_index) % len(MIXED_JOIN_CYCLE)]
        for edge_index in range(edge_count)
    )


def balanced_variant_rows(
    seed: Seed, seed_index: int
) -> Iterable[tuple[str, str, str, str, str]]:
    """Emit five shapes with deterministic, balanced mixed join labels."""
    edge_count = len(seed.predicates)
    vectors = [
        balanced_mixed_vector(seed_index, variant_index, edge_count)
        for variant_index in range(5)
    ]
    legacy_suffix_kinds = ("L", "R", "F")
    right_suffix_kind = legacy_suffix_kinds[(2 * seed_index + 1) % len(legacy_suffix_kinds)]

    left_vector, right_vector, third_vector, fourth_vector, fifth_vector = vectors
    yield (
        "ldmx",
        "".join(left_vector),
        "left_deep",
        "balanced mixed left-deep source-derived form",
        query_sql(
            seed,
            build_left_deep(seed, left_vector),
            "ldmx",
            "balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form",
        ),
    )
    yield (
        "rdmx",
        "".join(right_vector),
        "right_deep",
        "balanced mixed right-deep source-derived form",
        query_sql(
            seed,
            build_right_deep(seed, right_vector),
            "rdmx",
            "balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form",
        ),
    )

    bushy_eligible = bushy_root_partition(seed) is not None
    if bushy_eligible:
        yield (
            "bmx",
            "".join(third_vector),
            "bushy",
            "balanced mixed connected bushy source-derived form",
            query_sql(
                seed,
                build_bushy_mixed(seed, third_vector),
                "bmx",
                "balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form",
            ),
        )
    else:
        yield (
            "alt",
            "".join(third_vector),
            "left_deep",
            "balanced mixed alternate left-deep source-derived form",
            query_sql(
                seed,
                build_left_deep(seed, third_vector),
                "alt",
                "balanced mixed alternate form; bushy grouping is structurally ineligible",
            ),
        )

    if bushy_eligible:
        primary_bushy = build_bushy_mixed(seed, fourth_vector)
        alternate_bushy = build_bushy_mixed(seed, fourth_vector, alternate=True)
        if alternate_bushy == primary_bushy:
            raise ValueError(f"{seed.seed_id}: secondary bushy tree duplicates the primary tree")
        yield (
            "bdmx",
            "".join(fourth_vector),
            "bushy",
            "balanced mixed secondary connected bushy source-derived form",
            query_sql(
                seed,
                alternate_bushy,
                "bdmx",
                "balanced mixed secondary connected bushy source-derived form",
            ),
        )
    else:
        yield (
            "rdax",
            "".join(fourth_vector),
            "right_deep",
            "balanced mixed secondary right-deep source-derived form",
            query_sql(
                seed,
                build_secondary_right_deep(seed, fourth_vector),
                "rdax",
                "balanced mixed secondary right-deep source-derived form",
            ),
        )

    yield (
        f"rdu{right_suffix_kind}",
        "".join(fifth_vector),
        "right_deep",
        "balanced mixed alternate right-deep source-derived form",
        query_sql(
            seed,
            build_alternate_deep(seed, fifth_vector, right_deep=True),
            f"rdu{right_suffix_kind}",
            "balanced mixed alternate right-deep source-derived form",
        ),
    )


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


def v2_pattern_role(seed: Seed, suffix: str) -> str:
    """Tag the v1 strata motivating the sweep without selecting membership by speed."""
    if f"ojb_{seed.seed_id}_{suffix}" == "ojb_sqlstorm_job_11914_bdmx":
        return "job_regression_guard"
    hypothesis_variant = suffix in {"alt", "bmx", "bdmx"} or suffix.startswith("rdu")
    if seed.topology in {"star", "branch"} and hypothesis_variant:
        return "v1_advantage_hypothesis"
    return "paired_structural_control"


def add_v2_selectivity(
    sql: str, seed: Seed, tier: str, target: float, description: str,
) -> tuple[str, str]:
    """Replace the complete v1 filter with one semantic cohort."""
    spec = seed_filter_metadata(seed, tier[4:] if tier.startswith("sel_") else tier)
    metadata = (
        f"-- corpus_version: v2\n"
        f"-- selectivity_sweep: {tier}; intended band {description}\n"
        + semantic_comment(spec)
    )
    filtered = replace_where(sql, spec["selectivity_predicate"])
    return filtered.replace("SELECT ", metadata + "SELECT ", 1), spec["selectivity_anchor"]


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


def reset_generated_dir(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)


def regenerate_legacy_sources() -> None:
    """Reproduce legacy SQL before selecting pinned wins and business patterns."""
    cached = Path(importlib.util.cache_from_source(str(SCRIPT_DIR / "gen_queries.py")))
    if cached.is_file() and is_dataless(cached):
        cached.unlink()
    import gen_queries

    for generator in gen_queries.TARGETS["all"]:
        generator()
    for source in LEGACY_ROOT.glob("*/*.sql"):
        if str(source.relative_to(LEGACY_ROOT)) not in COMPLETED_QUERY_PATHS:
            source.unlink()


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


def generate_core(root: Path) -> int:
    core = root / "core"
    reset_generated_dir(core)
    manifest_rows: list[dict[str, str]] = []

    for seed_index, seed in enumerate(SEEDS):
        seed.validate()
        verify_source(seed)
        family_dir = core / seed.family
        family_dir.mkdir(parents=True, exist_ok=True)
        for suffix, vector, tree_shape, variant_semantics, sql in balanced_variant_rows(
            seed, seed_index
        ):
            query_id = f"ojb_{seed.seed_id}_{suffix}"
            relative_path = f"{seed.family}/{query_id}.sql"
            expected_graph = Counter(
                tuple(sorted(predicate_aliases(predicate))) for predicate in seed.predicates
            )
            if sql_join_graph(sql) != expected_graph:
                raise RuntimeError(f"{query_id}: emitted SQL changed the seed join graph")
            sql = sql.replace(
                "SELECT ",
                f"-- corpus_revision: {V1_CORPUS_REVISION}\n" + semantic_comment(seed_filter_metadata(seed)) + "SELECT ",
                1,
            )
            (core / relative_path).write_text(sql, encoding="utf-8")
            manifest_rows.append(
                {
                    "query_id": query_id,
                    "path": relative_path,
                    "corpus_revision": V1_CORPUS_REVISION,
                    "stratum": "benchmark_derived_core",
                    "family": seed.family,
                    "source_benchmark": seed.source_benchmark,
                    "source_version": seed.source_version,
                    "source_query": seed.source_query,
                    "source_location": seed.source_location,
                    "source_sha256": seed.source_hash,
                    "transformation": "connected_join_subgraph_adaptation+semantic_business_cohort",
                    "topology": seed.topology,
                    "tree_shape": tree_shape,
                    "join_vector": vector,
                    "relation_count": str(len(seed.relations)),
                    "predicate_class": "null_rejecting_outeryan_applicable",
                    "semantic_role": variant_semantics,
                    "semantics": seed_filter_metadata(seed)["filter_semantics"],
                    **seed_filter_metadata(seed),
                }
            )

    fields = list(manifest_rows[0])
    with (root / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest_rows)
    if len(manifest_rows) != CORE_QUERY_COUNT:
        raise RuntimeError(
            f"core size must match the {CORE_QUERY_COUNT} completed legacy cases; "
            f"generated {len(manifest_rows)}"
        )
    return len(manifest_rows)


def generate_supplemental(root: Path) -> int:
    supplemental = root / "supplemental"
    reset_generated_dir(supplemental)
    rows: list[dict[str, str]] = []
    for family, filename, speedup in LEGACY_OUTERYAN_WINS:
        source = LEGACY_ROOT / family / filename
        if not source.is_file():
            raise FileNotFoundError(f"legacy stress query not found: {source}")
        destination = supplemental / family / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        rows.append(
            {
                "query_id": source.stem,
                "path": f"{family}/{filename}",
                "stratum": "synthetic_optimizer_stress",
                "family": family,
                "provenance": "DuckOuterYan legacy generator",
                "industry_status": "not_industry_derived",
                "selection_policy": LEGACY_WIN_SELECTION_POLICY,
                "observed_tm_speedup": speedup,
                "content_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )

    fields = list(rows[0])
    with (supplemental / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def generate_industry_inspired(root: Path) -> int:
    """Materialize graph-preserving evaluation controls with mixed join labels."""
    destination_root = root / "industry_inspired"
    reset_generated_dir(destination_root)
    rows: list[dict[str, str]] = []
    with (root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        core_rows = list(csv.DictReader(handle))
    join_counts: Counter[str] = Counter()
    for row in core_rows:
        join_counts.update(row["join_vector"])
    control_index = 0

    def graph_structure(filename: str) -> tuple[str, str]:
        if filename.startswith("bushy"):
            return "branched", "bushy"
        if filename.startswith("rdeep"):
            return "chain", "right_deep"
        if filename.startswith("line"):
            return "chain", "left_deep"
        raise ValueError(f"unknown graph control structure: {filename}")

    def relabel_control(source_sql: str, *, flatten_aggregate: bool) -> tuple[str, str, int, dict]:
        nonlocal control_index
        normalized = normalize_active_sql(
            source_sql,
            flatten_aggregate=flatten_aggregate,
        )
        edge_count = sql_join_keyword_count(normalized)
        vector = next_balanced_control_vector(edge_count, join_counts, control_index)
        filter_metadata = control_filter_metadata(normalized, family, control_index)
        control_index += 1
        join_counts.update(vector)
        mixed = rewrite_join_types(normalized, vector)
        mixed = replace_where(mixed, filter_metadata["selectivity_predicate"])
        metadata = (
            f"-- corpus_revision: {V1_CORPUS_REVISION}\n"
            "-- workload_role: retained evaluation control with deterministic mixed joins\n"
            f"-- join_vector: {''.join(vector)}; relation graph retained; semantic filter replaced\n"
            + semantic_comment(filter_metadata)
        )
        return metadata + mixed, "".join(vector), edge_count, filter_metadata

    wins = {
        (family, filename): speedup
        for family, filename, speedup in LEGACY_OUTERYAN_WINS
    }
    pattern_keys = {
        (family, filename)
        for family, filename, _, _ in INDUSTRY_INSPIRED_PATTERNS
    }

    for family, filename, pattern_class, semantics in INDUSTRY_INSPIRED_PATTERNS:
        source = LEGACY_ROOT / family / filename
        if not source.is_file():
            raise FileNotFoundError(f"industry-inspired source query not found: {source}")
        destination = destination_root / family / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_sql = source.read_text(encoding="utf-8")
        normalized_sql, join_vector, edge_count, filter_metadata = relabel_control(
            source_sql,
            flatten_aggregate=(family, filename) in ACTIVE_AGGREGATE_SOURCES,
        )
        destination.write_text(normalized_sql, encoding="utf-8")
        observed_speedup = wins.get((family, filename), "")
        rows.append(
            {
                "query_id": source.stem,
                "path": f"{family}/{filename}",
                "corpus_revision": V1_CORPUS_REVISION,
                "evaluation_role": (
                    "industry_pattern_and_legacy_performance_win"
                    if observed_speedup
                    else "industry_pattern"
                ),
                "stratum": "industry_inspired_synthetic",
                "family": family,
                "source": f"outerjoin_query_old/{family}/{filename}",
                "pattern_class": pattern_class,
                "semantics": semantics,
                "industry_status": "industry_inspired_not_industry_derived",
                "production_source_id": "none",
                "selection_policy": (
                    ACTIVE_LEGACY_SOURCE_SELECTION_POLICY if observed_speedup else ""
                ),
                "historical_full_join_tm_speedup": observed_speedup,
                "measurement_status": "requires_v1_mixed_rerun",
                "provenance_class": "industry_synthetic_control",
                "topology": "",
                "tree_shape": "",
                "join_vector": join_vector,
                "relation_count": str(edge_count + 1),
                "source_content_sha256": hashlib.sha256(source_sql.encode("utf-8")).hexdigest(),
                "active_transformation": "graph_preserving_balanced_mixed_join_relabeling",
                "content_sha256": hashlib.sha256(normalized_sql.encode("utf-8")).hexdigest(),
                **filter_metadata,
            }
        )

    for family, filename, speedup in LEGACY_OUTERYAN_WINS:
        if (family, filename) in pattern_keys or family == "graph":
            continue
        source = LEGACY_ROOT / family / filename
        if not source.is_file():
            raise FileNotFoundError(f"legacy performance-win query not found: {source}")
        destination = destination_root / family / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_sql = source.read_text(encoding="utf-8")
        normalized_sql, join_vector, edge_count, filter_metadata = relabel_control(
            source_sql,
            flatten_aggregate=False,
        )
        destination.write_text(normalized_sql, encoding="utf-8")
        rows.append(
            {
                "query_id": source.stem,
                "path": f"{family}/{filename}",
                "corpus_revision": V1_CORPUS_REVISION,
                "evaluation_role": "legacy_performance_win",
                "stratum": "synthetic_optimizer_stress",
                "family": family,
                "source": f"outerjoin_query_old/{family}/{filename}",
                "pattern_class": "observed_outeryan_speedup",
                "semantics": (
                    "A legacy schema-synthetic query with a previously observed "
                    "OuterYan speedup; the active SQL is applicability-normalized."
                ),
                "industry_status": "not_industry_derived",
                "production_source_id": "none",
                "selection_policy": ACTIVE_LEGACY_SOURCE_SELECTION_POLICY,
                "historical_full_join_tm_speedup": speedup,
                "measurement_status": "requires_v1_mixed_rerun",
                "provenance_class": "schema_synthetic_control",
                "topology": "",
                "tree_shape": "",
                "join_vector": join_vector,
                "relation_count": str(edge_count + 1),
                "source_content_sha256": hashlib.sha256(source_sql.encode("utf-8")).hexdigest(),
                "active_transformation": "graph_preserving_balanced_mixed_join_relabeling",
                "content_sha256": hashlib.sha256(normalized_sql.encode("utf-8")).hexdigest(),
                **filter_metadata,
            }
        )

    for filename in GRAPH_CONTROL_FILENAMES:
        family = "graph"
        source = LEGACY_ROOT / family / filename
        if not source.is_file():
            raise FileNotFoundError(f"graph control source query not found: {source}")
        destination = destination_root / family / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_sql = source.read_text(encoding="utf-8")
        normalized_sql, join_vector, edge_count, filter_metadata = relabel_control(
            source_sql,
            flatten_aggregate=False,
        )
        destination.write_text(normalized_sql, encoding="utf-8")
        topology, tree_shape = graph_structure(filename)
        rows.append(
            {
                "query_id": source.stem,
                "path": f"{family}/{filename}",
                "corpus_revision": V1_CORPUS_REVISION,
                "evaluation_role": "graph_pattern",
                "stratum": "graph_synthetic_control",
                "family": family,
                "source": f"outerjoin_query_old/{family}/{filename}",
                "pattern_class": "graph_join_pattern",
                "semantics": (
                    "A generated multi-hop graph pattern over repeated edge relations; "
                    "the complete completed Graph suite is retained."
                ),
                "industry_status": "not_industry_derived",
                "production_source_id": "none",
                "selection_policy": GRAPH_CONTROL_SELECTION_POLICY,
                "historical_full_join_tm_speedup": wins.get((family, filename), ""),
                "measurement_status": "requires_v1_mixed_rerun",
                "provenance_class": "graph_synthetic_control",
                "topology": topology,
                "tree_shape": tree_shape,
                "join_vector": join_vector,
                "relation_count": str(edge_count + 1),
                "source_content_sha256": hashlib.sha256(source_sql.encode("utf-8")).hexdigest(),
                "active_transformation": "graph_preserving_balanced_mixed_join_relabeling",
                "content_sha256": hashlib.sha256(normalized_sql.encode("utf-8")).hexdigest(),
                **filter_metadata,
            }
        )

    expected_paths = {
        f"{family}/{filename}"
        for family, filename in (
            pattern_keys | set(wins) | {("graph", name) for name in GRAPH_CONTROL_FILENAMES}
        )
    }
    actual_paths = {row["path"] for row in rows}
    if (
        actual_paths != expected_paths
        or len(actual_paths) != len(rows)
        or len(rows) != INDUSTRY_EVALUATION_QUERY_COUNT
    ):
        raise RuntimeError(
            "industry evaluation membership mismatch: "
            f"expected_count={INDUSTRY_EVALUATION_QUERY_COUNT}, actual_count={len(rows)}, "
            f"missing={sorted(expected_paths - actual_paths)}, "
            f"unexpected={sorted(actual_paths - expected_paths)}"
        )
    if any(len(set(row["join_vector"])) < 2 for row in rows):
        raise RuntimeError("v1 evaluation control contains a single-kind join vector")
    if max(join_counts.values()) - min(join_counts.values()) > 1:
        raise RuntimeError(f"v1 benchmark join labels are imbalanced: {join_counts}")

    fields = list(rows[0])
    with (destination_root / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def generate_active_benchmark(root: Path, include_industry: bool = True) -> int:
    """Materialize the current mixed v1 corpus without obsolete timeout filtering."""
    destination_root = root / "benchmark"
    rows: list[dict[str, str]] = []

    with (root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        core_rows = list(csv.DictReader(handle))
    for row in core_rows:
        family = row["family"]
        source = root / "core" / row["path"]
        query_id = active_query_id("derived", row)
        content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        rows.append(
            {
                "query_id": query_id,
                "path": f"{family}/{query_id}.sql",
                "query_class": "derived",
                "evaluation_role": "benchmark_derived",
                "family": family,
                "source_component": "core",
                "source_path": f"core/{row['path']}",
                "source_content_sha256": content_sha256,
                "content_sha256": content_sha256,
                "corpus_revision": V1_CORPUS_REVISION,
                "provenance_class": "benchmark_source_derived",
                "source_benchmark": row["source_benchmark"],
                "source_query": row["source_query"],
                "source_location": row["source_location"],
                "topology": row["topology"],
                "tree_shape": row["tree_shape"],
                "join_vector": row["join_vector"],
                "relation_count": row["relation_count"],
                "predicate_class": row["predicate_class"],
                **copy_filter_metadata(row),
            }
        )

    if include_industry:
        with (root / "industry_inspired" / "manifest.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            industry_rows = list(csv.DictReader(handle))
        role_prefix = {
            "industry_pattern": ("industry", "industry"),
            "industry_pattern_and_legacy_performance_win": (
                "industry",
                "industry",
            ),
            "graph_pattern": ("derived", "derived"),
            "legacy_performance_win": ("derived", "derived"),
        }
        for row in industry_rows:
            role = row["evaluation_role"]
            if role not in role_prefix:
                raise RuntimeError(f"unknown industry evaluation role: {role}")
            prefix, query_class = role_prefix[role]
            family = row["family"]
            source = root / "industry_inspired" / row["path"]
            query_id = active_query_id(prefix, row)
            content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
            rows.append(
                {
                    "query_id": query_id,
                    "path": f"{family}/{query_id}.sql",
                    "query_class": query_class,
                    "evaluation_role": role,
                    "family": family,
                    "source_component": "industry_inspired",
                    "source_path": f"industry_inspired/{row['path']}",
                    "source_content_sha256": row["source_content_sha256"],
                    "content_sha256": content_sha256,
                    "corpus_revision": V1_CORPUS_REVISION,
                    "provenance_class": row["provenance_class"],
                    "source_benchmark": "",
                    "source_query": "",
                    "source_location": row["source"],
                    "topology": row["topology"],
                    "tree_shape": row["tree_shape"],
                    "join_vector": row["join_vector"],
                    "relation_count": row["relation_count"],
                    "predicate_class": "evaluation_control",
                    **copy_filter_metadata(row),
                }
            )

    expected_count = CORE_QUERY_COUNT + (INDUSTRY_EVALUATION_QUERY_COUNT if include_industry else 0)
    paths = {row["path"] for row in rows}
    if len(rows) != expected_count or len(paths) != expected_count:
        raise RuntimeError(
            "unfiltered benchmark membership mismatch: "
            f"expected={expected_count}, rows={len(rows)}, unique_paths={len(paths)}"
        )

    expected_active_count = ACTIVE_BENCHMARK_QUERY_COUNT if include_industry else ACTIVE_CORE_QUERY_COUNT
    if len(rows) != expected_active_count:
        raise RuntimeError(f"unexpected active benchmark count: {len(rows)}")
    validate_active_coverage(core_rows, rows, include_industry)

    # Only replace files owned by the previous manifest; preserve unrelated
    # files (including local manifest copies) in this generated directory.
    previous_manifest = destination_root / "manifest.csv"
    previous_rows = []
    if previous_manifest.exists():
        with previous_manifest.open(newline="", encoding="utf-8") as handle:
            previous_rows = list(csv.DictReader(handle))
    previous_paths = set()
    for row in previous_rows:
        relative_path = Path(row["path"])
        if (
            len(relative_path.parts) != 2
            or relative_path.parts[0] not in {"graph", "tpch", "tpcds", "job"}
            or relative_path.suffix != ".sql"
        ):
            raise RuntimeError(f"invalid generated SQL path: {relative_path}")
        previous_paths.add(row["path"])
        destination = destination_root / relative_path
        if (
            destination.exists()
            and hashlib.sha256(destination.read_bytes()).hexdigest() != row["content_sha256"]
        ):
            raise RuntimeError(
                f"locally modified active SQL; preserve changes before regenerating: {relative_path}"
            )
    actual_paths = {
        str(path.relative_to(destination_root)) for path in destination_root.glob("*/*.sql")
    }
    if actual_paths - previous_paths:
        raise RuntimeError(
            "unmanaged active SQL; preserve files before regenerating: "
            f"{sorted(actual_paths - previous_paths)}"
        )
    paths = {row["path"] for row in rows}
    for relative_path in sorted(previous_paths - paths):
        destination = destination_root / relative_path
        if destination.exists():
            destination.unlink()
    destination_root.mkdir(parents=True, exist_ok=True)
    for row in rows:
        destination = destination_root / row["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / row["source_path"], destination)
    fields = list(rows[0])
    with (destination_root / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def validate_active_coverage(
    core_rows: list[dict[str, str]], active_rows: list[dict[str, str]], include_industry: bool
) -> None:
    """Require complete current-revision coverage; old timeout pins are obsolete."""
    paths = {row["path"] for row in active_rows}
    retained_core = [row for row in core_rows
                     if f"{row['family']}/{active_query_id('derived', row)}.sql" in paths]
    if len(retained_core) != ACTIVE_CORE_QUERY_COUNT:
        raise RuntimeError(f"unexpected active core count: {len(retained_core)}")
    for dimension in ("tree_shape", "topology", "relation_count", "join_vector"):
        before = Counter(row[dimension] for row in core_rows)
        after = Counter(row[dimension] for row in retained_core)
        if before != after:
            raise RuntimeError(f"active core changed {dimension} coverage")
        before_family = {(row["family"], row[dimension]) for row in core_rows}
        after_family = {(row["family"], row[dimension]) for row in retained_core}
        if before_family != after_family:
            raise RuntimeError(f"active core lost family/{dimension} coverage")


def generate_timeout_manifest(root: Path) -> int:
    rows = [
        {
            "path": query.path,
            "family": Path(query.path).parent.name,
            "query_id": Path(query.path).stem,
            "disposition": "excluded_timeout",
            "reference_result": REFERENCE_RUN,
            "reference_note": "TIMEOUT",
        }
        for query in LEGACY_QUERIES
        if query.timed_out
    ]
    fields = list(rows[0])
    with (root / "timeout_exclusions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def classify_legacy(root: Path) -> int:
    retained = {f"{family}/{filename}" for family, filename, _ in LEGACY_OUTERYAN_WINS}
    industry_inspired = {
        f"{family}/{filename}"
        for family, filename, _, _ in INDUSTRY_INSPIRED_PATTERNS
    }
    rows: list[dict[str, str]] = []
    for query in LEGACY_QUERIES:
        relative = query.path
        source = LEGACY_ROOT / relative
        family = source.parent.name
        if query.timed_out:
            # Only the exclusion metadata remains; the archived SQL was retired.
            content_sha256 = ""
            content_status = "removed_timeout_sql"
        elif not source.is_file():
            raise FileNotFoundError(f"classified legacy query not found: {source}")
        elif is_dataless(source):
            content_sha256 = ""
            content_status = "icloud_dataless_not_read"
        else:
            content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
            content_status = "verified"
        if relative in TIMEOUT_QUERY_PATHS:
            disposition = "excluded_timeout"
            provenance = "legacy_timeout"
            reason = f"excluded by {REFERENCE_RUN}"
        elif relative in retained and relative in industry_inspired:
            disposition = "retain_industry_pattern_and_performance_win"
            provenance = "industry_inspired_synthetic+synthetic_optimizer_stress"
            reason = (
                "business-role pattern and pinned legacy OuterYan performance win; "
                "no production source is claimed"
            )
        elif relative in retained:
            disposition = "retain_performance_win"
            provenance = "synthetic_optimizer_stress"
            reason = (
                "retained in supplemental and industry evaluation corpora as a "
                "pinned legacy OuterYan performance win"
            )
        elif relative in industry_inspired:
            disposition = "retain_industry_pattern"
            provenance = "industry_inspired_synthetic"
            reason = "business-role pattern retained separately; no production source is claimed"
        elif "_real_" in source.stem:
            disposition = "archive_candidate"
            provenance = "benchmark_inspired_unmapped"
            reason = "business interpretation exists, but no exact source-query transformation is recorded"
        else:
            disposition = "archive_candidate"
            provenance = "schema_derived_synthetic"
            reason = "manual topology/vector generation without an upstream source-query mapping"
        rows.append(
            {
                "path": relative,
                "family": family,
                "disposition": disposition,
                "provenance_class": provenance,
                "reason": reason,
                "content_sha256": content_sha256,
                "content_status": content_status,
            }
        )

    fields = list(rows[0])
    with (root / "legacy_classification.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def validate_generated(root: Path, include_industry: bool = True) -> None:
    manifest_rows: list[dict[str, str]] = []
    manifest_paths: set[str] = set()
    with (root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            manifest_rows.append(row)
            manifest_paths.add(row["path"])

    actual_paths = {
        str(path.relative_to(root / "core"))
        for path in (root / "core").glob("*/*.sql")
    }
    if manifest_paths != actual_paths:
        missing = sorted(actual_paths - manifest_paths)
        stale = sorted(manifest_paths - actual_paths)
        raise RuntimeError(f"manifest mismatch: missing={missing}, stale={stale}")

    suffix_counts = Counter(row["query_id"].rsplit("_", 1)[-1] for row in manifest_rows)
    if suffix_counts["ldmx"] != len(SEEDS) or suffix_counts["rdmx"] != len(SEEDS):
        raise RuntimeError(f"every seed must have one ldmx/rdmx pair: {suffix_counts}")
    if suffix_counts["bmx"] + suffix_counts["alt"] != len(SEEDS):
        raise RuntimeError(f"every seed must have exactly one bmx/alt variant: {suffix_counts}")
    if suffix_counts["bdmx"] + suffix_counts["rdax"] != len(SEEDS):
        raise RuntimeError(f"every seed must have exactly one bdmx/rdax variant: {suffix_counts}")
    rdu_count = sum(
        count for suffix, count in suffix_counts.items() if suffix.startswith("rdu")
    )
    if rdu_count != len(SEEDS):
        raise RuntimeError(f"every seed must have exactly one rduX variant: {suffix_counts}")

    if any(row["corpus_revision"] != V1_CORPUS_REVISION for row in manifest_rows):
        raise RuntimeError("v1 core manifest has a stale corpus revision")
    if {row["source_benchmark"] for row in manifest_rows} != SOURCE_BENCHMARKS:
        raise RuntimeError("v1 core source provenance is incomplete")
    if any(len(set(row["join_vector"])) < 2 for row in manifest_rows):
        raise RuntimeError("v1 core contains a single-kind join vector")
    if any(
        int(row["relation_count"]) >= 5
        and set(row["join_vector"]) != set(MIXED_JOIN_CYCLE)
        for row in manifest_rows
    ):
        raise RuntimeError("a v1 query with at least four edges does not cover I/L/R/F")
    join_counts: Counter[str] = Counter()
    grouped_join_counts: dict[tuple[str, str], Counter[str]] = {}
    for row in manifest_rows:
        join_counts.update(row["join_vector"])
        group = (row["family"], row["tree_shape"])
        grouped_join_counts.setdefault(group, Counter()).update(row["join_vector"])
    if max(join_counts.values()) - min(join_counts.values()) > 1:
        raise RuntimeError(f"v1 core join labels are imbalanced: {join_counts}")
    if any(max(counts.values()) - min(counts.values()) > 3 for counts in grouped_join_counts.values()):
        raise RuntimeError(f"v1 family/shape join labels are imbalanced: {grouped_join_counts}")
    all_shapes = Counter(row["tree_shape"] for row in manifest_rows)
    if all_shapes != Counter({"left_deep": 45, "right_deep": 79, "bushy": 46}):
        raise RuntimeError(f"unexpected core shape distribution: {all_shapes}")
    predicate_classes = Counter(row["predicate_class"] for row in manifest_rows)
    if predicate_classes != Counter({"null_rejecting_outeryan_applicable": CORE_QUERY_COUNT}):
        raise RuntimeError(f"unsupported predicate classes in core: {predicate_classes}")

    for relative_path in sorted(actual_paths):
        sql = (root / "core" / relative_path).read_text(encoding="utf-8")
        upper = sql.upper()
        statement = "\n".join(
            line for line in upper.splitlines() if not line.lstrip().startswith("--")
        )
        if "OUTER JOIN" not in upper:
            raise RuntimeError(f"{relative_path}: no outer join")
        if " ON 1=1" in upper:
            raise RuntimeError(f"{relative_path}: cross product")
        if any(token in upper for token in ("GROUP BY", "SELECT DISTINCT", " OVER (")):
            raise RuntimeError(f"{relative_path}: outside core applicability envelope")
        null_tolerant_patterns = (
            r"\bIS\s+NULL\b",
            r"\bIS\s+(?:NOT\s+)?DISTINCT\s+FROM\b",
            r"\b(?:COALESCE|IFNULL)\s*\(",
        )
        if any(re.search(pattern, statement) for pattern in null_tolerant_patterns):
            raise RuntimeError(f"{relative_path}: NULL-tolerant predicate is not allowed in the core")
        row = next(row for row in manifest_rows if row["path"] == relative_path)
        validate_semantic_query(sql, row)
        if f"-- corpus_revision: {V1_CORPUS_REVISION}" not in sql:
            raise RuntimeError(f"{relative_path}: missing corpus revision")
        if sql_join_kind_counts(sql) != Counter(row["join_vector"]):
            raise RuntimeError(f"{relative_path}: SQL and manifest join labels differ")

    active_root = root / "benchmark"
    with (active_root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        active_rows = list(csv.DictReader(handle))
    active_paths = {
        str(path.relative_to(active_root)) for path in active_root.glob("*/*.sql")
    }
    expected_active_count = ACTIVE_BENCHMARK_QUERY_COUNT if include_industry else ACTIVE_CORE_QUERY_COUNT
    if len(active_rows) != expected_active_count or {
        row["path"] for row in active_rows
    } != active_paths:
        raise RuntimeError("active benchmark manifest does not match generated SQL")
    validate_active_coverage(manifest_rows, active_rows, include_industry)
    valid_prefixes = ("derived__", "industry__")
    if any(not row["query_id"].startswith(valid_prefixes) for row in active_rows):
        raise RuntimeError("active benchmark query is missing its provenance prefix")
    active_join_counts: Counter[str] = Counter()
    for row in active_rows:
        relative_path = row["path"]
        sql = (active_root / relative_path).read_text(encoding="utf-8")
        validate_semantic_query(sql, row)
        statement = "\n".join(
            line for line in sql.upper().splitlines() if not line.lstrip().startswith("--")
        )
        if any(token in statement for token in ("GROUP BY", "SELECT DISTINCT", " OVER (")):
            raise RuntimeError(f"{relative_path}: active query bypasses OuterYan")
        if row["corpus_revision"] != V1_CORPUS_REVISION:
            raise RuntimeError(f"{relative_path}: stale active corpus revision")
        if len(set(row["join_vector"])) < 2:
            raise RuntimeError(f"{relative_path}: single-kind active join vector")
        if sql_join_kind_counts(sql) != Counter(row["join_vector"]):
            raise RuntimeError(f"{relative_path}: SQL and active manifest join labels differ")
        if hashlib.sha256(sql.encode("utf-8")).hexdigest() != row["content_sha256"]:
            raise RuntimeError(f"{relative_path}: active content hash mismatch")
        active_join_counts.update(row["join_vector"])
    if max(active_join_counts.values()) - min(active_join_counts.values()) > 1:
        raise RuntimeError(f"v1 active join labels are imbalanced: {active_join_counts}")


def generate_v2_core(root: Path) -> int:
    """Expand every source-derived structural variant across three semantic bands."""
    core = root / "core"
    reset_generated_dir(core)
    rows: list[dict[str, str]] = []
    design_basis = (
        "all source seeds and five tree variants are included without timing-based "
        "selection; I/L/R/F labels follow a deterministic balanced rotation and each "
        "base keeps the same vector at every selectivity tier"
    )
    for seed_index, seed in enumerate(SEEDS):
        seed.validate()
        if seed.source_benchmark not in SOURCE_BENCHMARKS:
            raise RuntimeError(
                f"{seed.seed_id}: unsupported v2 source benchmark {seed.source_benchmark}"
            )
        verify_source(seed)
        family_dir = core / seed.family
        family_dir.mkdir(parents=True, exist_ok=True)
        expected_graph = Counter(
            tuple(sorted(predicate_aliases(predicate))) for predicate in seed.predicates
        )
        for suffix, vector, tree_shape, variant_semantics, base_sql in balanced_variant_rows(
            seed, seed_index
        ):
            base_query_id = f"ojb_{seed.seed_id}_{suffix}"
            for tier, target, description in V2_SELECTIVITY_TIERS:
                query_id = f"{base_query_id}_{tier}"
                relative_path = f"{seed.family}/{query_id}.sql"
                sql, anchor = add_v2_selectivity(
                    base_sql, seed, tier, target, description
                )
                if sql_join_graph(sql) != expected_graph:
                    raise RuntimeError(f"{query_id}: emitted SQL changed the seed join graph")
                (core / relative_path).write_text(sql, encoding="utf-8")
                rows.append(
                    {
                        "query_id": query_id,
                        "path": relative_path,
                        "corpus_version": "v2",
                        "base_query_id": base_query_id,
                        "stratum": "benchmark_derived_v2_core",
                        "family": seed.family,
                        "source_benchmark": seed.source_benchmark,
                        "source_version": seed.source_version,
                        "source_query": seed.source_query,
                        "source_location": seed.source_location,
                        "source_sha256": seed.source_hash,
                        "transformation": (
                            "connected_join_subgraph_adaptation+"
                            "semantic_business_range_sweep"
                        ),
                        "topology": seed.topology,
                        "tree_shape": tree_shape,
                        "join_vector": vector,
                        "relation_count": str(len(seed.relations)),
                        "predicate_class": "null_rejecting_outeryan_applicable",
                        "semantic_role": variant_semantics,
                        "semantics": seed_filter_metadata(seed)["filter_semantics"],
                        **seed_filter_metadata(seed, tier[4:] if tier.startswith("sel_") else tier),
                        "pattern_role": v2_pattern_role(seed, suffix),
                        "design_basis": design_basis,
                    }
                )
    fields = list(rows[0])
    with (root / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    if len(rows) != V2_CORE_QUERY_COUNT:
        raise RuntimeError(f"unexpected v2 core count: {len(rows)}")
    return len(rows)


def v3_aggregate_schedule() -> list[str]:
    """Return a deterministic, evenly interleaved weighted aggregate schedule."""
    total = V3_BENCHMARK_QUERY_COUNT
    assigned: Counter[str] = Counter()
    order = {variant: index for index, variant in enumerate(V3_AGGREGATE_VARIANTS)}
    schedule: list[str] = []
    for slot in range(total):
        available = [
            variant
            for variant, target in V3_AGGREGATE_TARGET_COUNTS.items()
            if assigned[variant] < target
        ]
        # Largest cumulative quota deficit first. Integer arithmetic makes the
        # mapping stable and independent of Python floating-point behavior.
        aggregate_variant = max(
            available,
            key=lambda variant: (
                (slot + 1) * V3_AGGREGATE_TARGET_COUNTS[variant]
                - assigned[variant] * total,
                V3_AGGREGATE_TARGET_COUNTS[variant],
                -order[variant],
            ),
        )
        assigned[aggregate_variant] += 1
        schedule.append(aggregate_variant)
    if assigned != Counter(V3_AGGREGATE_TARGET_COUNTS):
        raise RuntimeError(f"v3 aggregate schedule missed its targets: {assigned}")
    return schedule


def generate_v3_core(root: Path) -> int:
    """Generate one aggregate form for each of three shapes of every source seed."""
    core = root / "core"
    reset_generated_dir(core)
    rows: list[dict[str, str]] = []
    design_basis = (
        "all 34 source-derived seeds are included without timing-based selection; "
        "each contributes its first three deterministic mixed-join structural variants, "
        "aggregate forms follow a fixed weighted schedule using only structural "
        "slot order (COUNT=42, SUM=30, MIN=15, MAX=15); MIN and MAX split one "
        "extremum class equally, and no timing or result file affects assignment"
    )
    aggregate_schedule = v3_aggregate_schedule()
    for seed_index, seed in enumerate(SEEDS):
        seed.validate()
        if seed.source_benchmark not in SOURCE_BENCHMARKS:
            raise RuntimeError(
                f"{seed.seed_id}: unsupported v3 source benchmark {seed.source_benchmark}"
            )
        verify_source(seed)
        family_dir = core / seed.family
        family_dir.mkdir(parents=True, exist_ok=True)
        expected_graph = Counter(
            tuple(sorted(predicate_aliases(predicate))) for predicate in seed.predicates
        )
        structural_variants = list(balanced_variant_rows(seed, seed_index))[
            :V3_VARIANTS_PER_SEED
        ]
        if len(structural_variants) != V3_VARIANTS_PER_SEED:
            raise RuntimeError(f"{seed.seed_id}: insufficient structural variants for v3")
        for variant_index, structural in enumerate(structural_variants):
            aggregate_variant = aggregate_schedule[
                seed_index * V3_VARIANTS_PER_SEED + variant_index
            ]
            suffix, vector, tree_shape, variant_semantics, base_sql = structural
            query_id = f"ojb_{seed.seed_id}_{suffix}_{aggregate_variant}"
            relative_path = f"{seed.family}/{query_id}.sql"
            sql, anchor = add_v3_aggregation(base_sql, seed, aggregate_variant)
            sql = sql.replace("SELECT ", semantic_comment(seed_filter_metadata(seed)) + "SELECT ", 1)
            if sql_join_graph(sql) != expected_graph:
                raise RuntimeError(f"{query_id}: emitted SQL changed the seed join graph")
            (core / relative_path).write_text(sql, encoding="utf-8")
            rows.append(
                {
                    "query_id": query_id,
                    "path": relative_path,
                    "corpus_version": "v3",
                    "base_query_id": f"ojb_{seed.seed_id}_{suffix}",
                    "stratum": "benchmark_derived_v3_aggregate_core",
                    "family": seed.family,
                    "source_benchmark": seed.source_benchmark,
                    "source_version": seed.source_version,
                    "source_query": seed.source_query,
                    "source_location": seed.source_location,
                    "source_sha256": seed.source_hash,
                    "transformation": (
                        "connected_join_subgraph_adaptation+root_aggregation"
                    ),
                    "topology": seed.topology,
                    "tree_shape": tree_shape,
                    "join_vector": vector,
                    "relation_count": str(len(seed.relations)),
                    "predicate_class": "null_rejecting_outeryan_applicable",
                    "semantic_role": variant_semantics,
                    "semantics": seed_filter_metadata(seed)["filter_semantics"],
                    "aggregate_variant": aggregate_variant,
                    "aggregate_anchor": anchor,
                    **seed_filter_metadata(seed),
                    "design_basis": design_basis,
                }
            )
    fields = list(rows[0])
    with (root / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    if len(rows) != V3_BENCHMARK_QUERY_COUNT:
        raise RuntimeError(f"unexpected v3 core count: {len(rows)}")
    return len(rows)


def generate_v3_benchmark(root: Path) -> int:
    """Materialize the v3 aggregation core as a harness-ready benchmark."""
    destination_root = root / "benchmark"
    reset_generated_dir(destination_root)
    with (root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        core_rows = list(csv.DictReader(handle))
    rows: list[dict[str, str]] = []
    for row in core_rows:
        source = root / "core" / row["path"]
        query_id = active_query_id("aggregate", row)
        destination_path = f"{row['family']}/{query_id}.sql"
        destination = destination_root / destination_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        rows.append(
            {
                "query_id": query_id,
                "path": destination_path,
                "query_class": "aggregate",
                "evaluation_role": "benchmark_derived_v3_aggregate",
                "family": row["family"],
                "source_component": "core",
                "source_path": f"core/{row['path']}",
                "source_content_sha256": content_sha256,
                "content_sha256": content_sha256,
                "corpus_version": "v3",
                "base_query_id": row["base_query_id"],
                "provenance_class": "benchmark_source_derived",
                "source_benchmark": row["source_benchmark"],
                "source_query": row["source_query"],
                "source_location": row["source_location"],
                "topology": row["topology"],
                "tree_shape": row["tree_shape"],
                "join_vector": row["join_vector"],
                "relation_count": row["relation_count"],
                "predicate_class": row["predicate_class"],
                "aggregate_variant": row["aggregate_variant"],
                "aggregate_anchor": row["aggregate_anchor"],
                **copy_filter_metadata(row),
            }
        )
    fields = list(rows[0])
    with (destination_root / "manifest.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def sql_join_keyword_count(sql: str) -> int:
    """Count emitted join keywords while ignoring full-line SQL comments."""
    statement = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    return len(JOIN_KEYWORD_PATTERN.findall(statement))


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


def rewrite_join_types(sql: str, kinds: Sequence[str]) -> str:
    """Relabel an existing control tree without changing relations, edges, or grouping."""
    replacements = iter(kinds)
    replaced = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal replaced
        replaced += 1
        return JOIN_SQL[next(replacements)]

    output: list[str] = []
    for line in sql.splitlines(keepends=True):
        if line.lstrip().startswith("--"):
            output.append(line)
        else:
            output.append(JOIN_KEYWORD_PATTERN.sub(replace, line))
    if replaced != len(kinds):
        raise ValueError(
            f"join-vector length {len(kinds)} does not match {replaced} emitted joins"
        )
    return "".join(output)


def next_balanced_control_vector(
    edge_count: int, current_counts: Counter[str], control_index: int
) -> tuple[str, ...]:
    """Choose a mixed cyclic vector that minimizes the current global imbalance."""
    if edge_count < 2:
        raise ValueError("a mixed control requires at least two join edges")

    def candidate(offset: int) -> tuple[str, ...]:
        return tuple(
            MIXED_JOIN_CYCLE[(offset + edge_index) % len(MIXED_JOIN_CYCLE)]
            for edge_index in range(edge_count)
        )

    def score(offset: int) -> tuple[float, float, int]:
        counts = current_counts.copy()
        counts.update(candidate(offset))
        values = [counts[kind] for kind in MIXED_JOIN_CYCLE]
        mean = sum(values) / len(values)
        return (
            float(max(values) - min(values)),
            sum((value - mean) ** 2 for value in values),
            (offset - control_index) % len(MIXED_JOIN_CYCLE),
        )

    best_offset = min(range(len(MIXED_JOIN_CYCLE)), key=score)
    return candidate(best_offset)


def generate_v2_benchmark(root: Path, v1_root: Path = DEFAULT_ROOT) -> int:
    """Materialize the mixed v2 core and mixed Graph/industry/schema controls."""
    destination_root = root / "benchmark"
    reset_generated_dir(destination_root)
    rows: list[dict[str, str]] = []
    with (root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        core_rows = list(csv.DictReader(handle))
    join_counts: Counter[str] = Counter()
    for row in core_rows:
        source = root / "core" / row["path"]
        query_id = active_query_id("derived", row)
        destination_path = f"{row['family']}/{query_id}.sql"
        content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        join_counts.update(row["join_vector"])
        destination = destination_root / destination_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        rows.append(
            {
                "query_id": query_id,
                "path": destination_path,
                "query_class": "derived",
                "evaluation_role": "benchmark_derived_v2",
                "family": row["family"],
                "source_component": "core",
                "source_path": f"core/{row['path']}",
                "source_content_sha256": content_sha256,
                "content_sha256": content_sha256,
                "corpus_version": "v2",
                "base_query_id": row["base_query_id"],
                "provenance_class": "benchmark_source_derived",
                "source_benchmark": row["source_benchmark"],
                "source_query": row["source_query"],
                "source_location": row["source_location"],
                "topology": row["topology"],
                "tree_shape": row["tree_shape"],
                "join_vector": row["join_vector"],
                "relation_count": row["relation_count"],
                "predicate_class": row["predicate_class"],
                **copy_filter_metadata(row),
                "pattern_role": row["pattern_role"],
            }
        )

    v1_active = v1_root / "benchmark"
    with (v1_active / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        evaluation_rows = [
            row for row in csv.DictReader(handle)
            if row["evaluation_role"] != "benchmark_derived"
        ]
    if len(evaluation_rows) != V2_EVALUATION_QUERY_COUNT:
        raise RuntimeError(f"unexpected v1 evaluation-control count: {len(evaluation_rows)}")
    for control_index, row in enumerate(evaluation_rows):
        source = v1_active / row["path"]
        source_bytes = source.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        if source_sha256 != row["content_sha256"]:
            raise RuntimeError(f"v1 evaluation control changed: {row['query_id']}")
        source_sql = source_bytes.decode("utf-8")
        edge_count = sql_join_keyword_count(source_sql)
        vector = next_balanced_control_vector(edge_count, join_counts, control_index)
        join_counts.update(vector)
        metadata = (
            "-- corpus_version: v2\n"
            "-- workload_role: retained evaluation control with deterministic mixed joins\n"
            f"-- join_vector: {''.join(vector)}; relation and predicate structure unchanged\n"
        )
        mixed_sql = rewrite_join_types(source_sql, vector)
        mixed_sql = metadata + mixed_sql
        destination = destination_root / row["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(mixed_sql, encoding="utf-8")
        content_sha256 = hashlib.sha256(mixed_sql.encode("utf-8")).hexdigest()
        if row["family"] == "graph":
            provenance_class = "graph_synthetic_control"
        elif row["query_id"].startswith("industry__"):
            provenance_class = "industry_synthetic_control"
        else:
            provenance_class = "schema_synthetic_control"
        rows.append(
            {
                "query_id": row["query_id"],
                "path": row["path"],
                "query_class": row["query_class"],
                "evaluation_role": row["evaluation_role"],
                "family": row["family"],
                "source_component": "v1_active_evaluation",
                "source_path": f"../benchmark/{row['path']}",
                "source_content_sha256": source_sha256,
                "content_sha256": content_sha256,
                "corpus_version": "v2",
                "base_query_id": row["query_id"],
                "provenance_class": provenance_class,
                "source_benchmark": "",
                "source_query": "",
                "source_location": row["source_path"],
                "topology": row["topology"],
                "tree_shape": row["tree_shape"],
                "join_vector": "".join(vector),
                "relation_count": str(edge_count + 1),
                "predicate_class": "evaluation_control",
                **copy_filter_metadata(row),
                "pattern_role": (
                    "job_regression_guard"
                    if row["query_id"] == "derived__sem__oy_jb_jb_bushy4a_v2"
                    else "evaluation_control"
                ),
            }
        )

    if len(rows) != V2_BENCHMARK_QUERY_COUNT:
        raise RuntimeError(f"unexpected v2 benchmark count: {len(rows)}")
    paths = [row["path"] for row in rows]
    if len(paths) != len(set(paths)):
        raise RuntimeError("v2 benchmark contains duplicate paths")
    if max(join_counts.values()) - min(join_counts.values()) > 1:
        raise RuntimeError(f"v2 benchmark join labels are imbalanced: {join_counts}")
    fields = list(rows[0])
    with (destination_root / "manifest.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def v1_active_rows(v1_root: Path) -> dict[str, dict[str, str]]:
    manifest = v1_root / "benchmark" / "manifest.csv"
    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {row["query_id"]: row for row in rows}


def v3_stress_selection_rank(query_id: str) -> str:
    material = f"{V3_STRESS_SELECTION_SALT}:{query_id}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def select_v3_stress_bases(
    v2_root: Path = DEFAULT_V2_ROOT, v1_root: Path = DEFAULT_ROOT
) -> list[dict[str, str]]:
    """Select six balanced mixed bases from metadata only, never performance."""
    with (v2_root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        core_rows = list(csv.DictReader(handle))
    active_v1_base_ids = {
        Path(row["source_path"]).stem
        for row in v1_active_rows(v1_root).values()
        if row["evaluation_role"] == "benchmark_derived"
    }
    candidates: list[dict[str, str]] = []
    for metadata in core_rows:
        if metadata["selectivity_tier"] != V2_SELECTIVITY_TIERS[0][0]:
            continue
        if metadata["base_query_id"] not in active_v1_base_ids:
            continue
        if metadata["family"] not in SELECTIVITY_STRESS_FAMILIES:
            continue
        if (
            len(set(metadata["join_vector"])) < 2
            or int(metadata["relation_count"]) < SELECTIVITY_STRESS_MIN_RELATIONS
            or metadata["predicate_class"] != "null_rejecting_outeryan_applicable"
        ):
            continue
        source = v2_root / "core" / metadata["path"]
        source_sql = source.read_text(encoding="utf-8")
        if metadata["selectivity_predicate"] not in source_sql:
            continue
        candidate = dict(metadata)
        candidate.update(
            {
                "core_query_id": metadata["query_id"],
                "core_path": metadata["path"],
                "content_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "selection_rank": v3_stress_selection_rank(metadata["base_query_id"]),
            }
        )
        candidates.append(candidate)

    selected: list[dict[str, str]] = []
    for family in SELECTIVITY_STRESS_FAMILIES:
        used_sources: set[str] = set()
        for tree_shape, source_benchmark in V3_STRESS_SLOTS_BY_FAMILY[family]:
            eligible = [
                row for row in candidates
                if row["family"] == family
                and row["tree_shape"] == tree_shape
                and row["source_benchmark"] == source_benchmark
                and row["source_location"] not in used_sources
            ]
            if not eligible:
                raise RuntimeError(
                    f"no v3 selectivity-stress candidate for "
                    f"{family}/{tree_shape}/{source_benchmark}"
                )
            chosen = min(eligible, key=lambda row: row["selection_rank"])
            chosen = dict(
                chosen,
                selection_slot=(
                    f"tree_shape:{tree_shape};source_benchmark:{source_benchmark}"
                ),
            )
            selected.append(chosen)
            used_sources.add(chosen["source_location"])

    if len(selected) != V3_STRESS_BASE_COUNT:
        raise RuntimeError(f"unexpected v3 selectivity-stress base count: {len(selected)}")
    if Counter(row["tree_shape"] for row in selected) != Counter(
        {shape: 2 for shape in SELECTIVITY_STRESS_TREE_SHAPES}
    ):
        raise RuntimeError("v3 selectivity-stress bases are not shape-balanced")
    return selected


def generate_v3_selectivity_stress(
    root: Path, v2_root: Path = DEFAULT_V2_ROOT, v1_root: Path = DEFAULT_ROOT
) -> int:
    """Generate a compact, paired selectivity ablation under v3."""
    destination_root = root / "selectivity_stress"
    reset_generated_dir(destination_root)
    rows: list[dict[str, str]] = []
    selection_policy = (
        "mixed v2 counterparts of feasibility-screened active v1 source-derived core; "
        "static target domain "
        "(at least two join kinds, at least four relations, applicable predicate); "
        "two bases per TPC-H/TPC-DS/JOB execution family and two bases per "
        "left-deep/right-deep/bushy shape across the complete set; one native-source "
        "and one SQLStorm source per family, selected by fixed family/shape/source "
        "slots and salted SHA-256 rank; no timing or result input"
    )
    for base in select_v3_stress_bases(v2_root, v1_root):
        base_query_id = base["base_query_id"]
        family = base["family"]
        source = v2_root / "core" / base["core_path"]
        source_sql = source.read_text(encoding="utf-8")
        if hashlib.sha256(source.read_bytes()).hexdigest() != base["content_sha256"]:
            raise RuntimeError(f"v3 selectivity-stress base changed: {base_query_id}")
        for tier, semantic_tier, target_fraction, description in SELECTIVITY_STRESS_TIERS:
            query_id = f"stress__sem__{base_query_id}_{tier}"
            relative_path = f"{family}/{query_id}.sql"
            filter_metadata = semantic_metadata(base["selectivity_profile"], base["selectivity_anchor"], semantic_tier)
            filter_metadata["source_filter_adaptation"] = base["source_filter_adaptation"]
            sql = replace_where(source_sql, filter_metadata["selectivity_predicate"])
            sql = sql.replace(
                "-- corpus_version: v2\n",
                "-- corpus_version: v3\n-- derived_from_corpus_version: v2\n",
                1,
            )
            sql = re.sub(
                r"^-- (?:selectivity_sweep|semantic_filter|predicate|selectivity_scope):.*\n",
                "",
                sql,
                flags=re.MULTILINE,
            )
            metadata = (
                "-- workload_role: metadata-selected balanced selectivity ablation\n"
                f"-- selectivity_stress: {tier}; {description}\n"
                + semantic_comment(filter_metadata)
            )
            sql = sql.replace("SELECT ", metadata + "SELECT ", 1)
            destination = destination_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(sql, encoding="utf-8")
            rows.append(
                {
                    "query_id": query_id,
                    "path": relative_path,
                    "query_class": "selectivity_stress",
                    "family": family,
                    "corpus_version": "v3",
                    "base_query_id": base_query_id,
                    "source_path": f"../../v2/core/{base['core_path']}",
                    "source_content_sha256": base["content_sha256"],
                    "content_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                    "headline_eligible": "false",
                    "reporting_role": "selectivity_ablation",
                    "performance_selected": "false",
                    "selection_reference": "outerjoin_benchmark/v2/manifest.csv",
                    "selection_policy": selection_policy,
                    "selection_salt": V3_STRESS_SELECTION_SALT,
                    "selection_rank": base["selection_rank"],
                    "selection_slot": base["selection_slot"],
                    "source_benchmark": base["source_benchmark"],
                    "source_query": base["source_query"],
                    "source_location": base["source_location"],
                    "topology": base["topology"],
                    "tree_shape": base["tree_shape"],
                    "join_vector": base["join_vector"],
                    "predicate_class": base["predicate_class"],
                    "relation_count": base["relation_count"],
                    "eligibility_domain": (
                        "static metadata only: mixed I/L/R/F, relation_count>=4, "
                        "null-rejecting OuterYan-applicable predicate"
                    ),
                    **filter_metadata,
                    "selectivity_tier": tier,
                    "tier_balance": f"{V3_STRESS_BASE_COUNT} queries per tier",
                    "distribution_claim": (
                        "balanced tier counts; numeric levels and realized selectivity "
                        "are not claimed to be uniform"
                    ),
                    "benefit_hypothesis": (
                        "three paired selectivity levels measure where intermediate-result "
                        "reduction helps, plateaus, or becomes overhead"
                    ),
                }
            )
    if len(rows) != V3_STRESS_QUERY_COUNT:
        raise RuntimeError(f"unexpected selectivity-stress count: {len(rows)}")
    fields = list(rows[0])
    with (destination_root / "manifest.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def generate_v2_job_regressions(root: Path, v1_root: Path = DEFAULT_ROOT) -> int:
    """Expose mixed v2 counterparts of the two historical v1 JOB regressions."""
    destination_root = root / "job_regressions"
    reset_generated_dir(destination_root)
    with (root / "benchmark" / "manifest.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        benchmark_rows = list(csv.DictReader(handle))
    rows: list[dict[str, str]] = []
    for base_query_id, expected_hash, observed_speedup in V2_JOB_REGRESSIONS:
        expected_base_id = (
            base_query_id
            if base_query_id.startswith("ojb_")
            else f"derived__sem__{base_query_id}"
        )
        candidates = [
            row for row in benchmark_rows
            if row["base_query_id"] == expected_base_id
            and row["family"] == "job"
            and (row["evaluation_role"] != "benchmark_derived_v2"
                 or row["selectivity_tier"] == "sel_medium")
        ]
        if len(candidates) != 1:
            raise RuntimeError(f"missing mixed v2 JOB counterpart: {expected_base_id}")
        source_row = candidates[0]
        source = root / "benchmark" / source_row["path"]
        content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        if content_sha256 != source_row["content_sha256"]:
            raise RuntimeError(f"mixed v2 JOB counterpart changed: {expected_base_id}")
        query_id = f"regression__sem__{base_query_id}"
        relative_path = f"job/{query_id}.sql"
        destination = destination_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        rows.append(
            {
                "query_id": query_id,
                "path": relative_path,
                "query_class": "job_regression",
                "family": "job",
                "corpus_version": "v2",
                "base_query_id": base_query_id,
                "source_path": f"../benchmark/{source_row['path']}",
                "content_sha256": content_sha256,
                "join_vector": source_row["join_vector"],
                "headline_eligible": "false",
                "selection_reference": V2_0916_REFERENCE_RUN,
                "historical_v1_content_sha256": expected_hash,
                "historical_v1_observed_tm_speedup": observed_speedup,
                "selection_policy": (
                    "mixed v2 counterpart of an all-FULL v1 query with "
                    "selected_plan=OUTERYAN and tm_speedup<0.95 in the 0916 run"
                ),
                "measurement_status": "requires_v2_remeasurement",
                "disposition": "retain_mixed_counterpart_in_main_benchmark",
                "rationale": (
                    "changing join labels invalidates the old speedup, but retaining the "
                    "counterpart avoids silently dropping historically difficult structure"
                ),
            }
        )
    fields = list(rows[0])
    with (destination_root / "manifest.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def validate_v2_generated(root: Path) -> None:
    with (root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        core_rows = list(csv.DictReader(handle))
    core_paths = {
        str(path.relative_to(root / "core")) for path in (root / "core").glob("*/*.sql")
    }
    if len(core_rows) != V2_CORE_QUERY_COUNT or {row["path"] for row in core_rows} != core_paths:
        raise RuntimeError("v2 core manifest does not match generated SQL")
    tier_counts = Counter(row["selectivity_tier"] for row in core_rows)
    if tier_counts != Counter({tier: CORE_QUERY_COUNT for tier, _, _ in V2_SELECTIVITY_TIERS}):
        raise RuntimeError(f"unexpected v2 selectivity distribution: {tier_counts}")
    base_counts = Counter(row["base_query_id"] for row in core_rows)
    if set(base_counts.values()) != {len(V2_SELECTIVITY_TIERS)} or len(base_counts) != CORE_QUERY_COUNT:
        raise RuntimeError("v2 must contain every structural variant at every selectivity tier")
    base_vectors: dict[str, set[str]] = {}
    for row in core_rows:
        base_vectors.setdefault(row["base_query_id"], set()).add(row["join_vector"])
    if any(len(vectors) != 1 for vectors in base_vectors.values()):
        raise RuntimeError("selectivity tiers changed a base query's join vector")
    if {row["source_benchmark"] for row in core_rows} != SOURCE_BENCHMARKS:
        raise RuntimeError("v2 core source provenance is incomplete")
    if any(len(set(row["join_vector"])) < 2 for row in core_rows):
        raise RuntimeError("v2 core contains a single-kind join vector")
    if any(
        int(row["relation_count"]) >= 5
        and set(row["join_vector"]) != set(MIXED_JOIN_CYCLE)
        for row in core_rows
    ):
        raise RuntimeError("a v2 query with at least four edges does not cover I/L/R/F")
    unique_base_rows = [
        row for row in core_rows
        if row["selectivity_tier"] == V2_SELECTIVITY_TIERS[0][0]
    ]
    base_join_counts: Counter[str] = Counter()
    grouped_join_counts: dict[tuple[str, str], Counter[str]] = {}
    for row in unique_base_rows:
        base_join_counts.update(row["join_vector"])
        group = (row["family"], row["tree_shape"])
        grouped_join_counts.setdefault(group, Counter()).update(row["join_vector"])
    if max(base_join_counts.values()) - min(base_join_counts.values()) > 1:
        raise RuntimeError(f"v2 core join labels are imbalanced: {base_join_counts}")
    if any(max(counts.values()) - min(counts.values()) > 3 for counts in grouped_join_counts.values()):
        raise RuntimeError(f"v2 family/shape join labels are imbalanced: {grouped_join_counts}")
    for row in core_rows:
        sql = (root / "core" / row["path"]).read_text(encoding="utf-8")
        validate_semantic_query(sql, row)
        predicate = row["selectivity_predicate"]
        if predicate not in sql or "-- corpus_version: v2" not in sql:
            raise RuntimeError(f"{row['path']}: missing v2 selectivity provenance")
        if " ON 1=1" in sql.upper():
            raise RuntimeError(f"{row['path']}: cross product")
        if sql_join_kind_counts(sql) != Counter(row["join_vector"]):
            raise RuntimeError(f"{row['path']}: SQL and manifest join labels differ")

    active_root = root / "benchmark"
    with (active_root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        active_rows = list(csv.DictReader(handle))
    active_paths = {
        str(path.relative_to(active_root)) for path in active_root.glob("*/*.sql")
    }
    if len(active_rows) != V2_BENCHMARK_QUERY_COUNT or {
        row["path"] for row in active_rows
    } != active_paths:
        raise RuntimeError("v2 benchmark manifest does not match generated SQL")
    roles = Counter(row["evaluation_role"] for row in active_rows)
    if roles["benchmark_derived_v2"] != V2_CORE_QUERY_COUNT:
        raise RuntimeError(f"unexpected v2 benchmark roles: {roles}")
    regression_roles = {
        row["base_query_id"]: row["pattern_role"]
        for row in active_rows
        if row["pattern_role"] == "job_regression_guard"
    }
    if regression_roles != {
        "ojb_sqlstorm_job_11914_bdmx": "job_regression_guard",
        "derived__sem__oy_jb_jb_bushy4a_v2": "job_regression_guard",
    }:
        raise RuntimeError(f"unexpected v2 JOB regression tags: {regression_roles}")
    if any(len(set(row["join_vector"])) < 2 for row in active_rows):
        raise RuntimeError("v2 benchmark contains a single-kind join vector")
    active_join_counts: Counter[str] = Counter()
    for row in active_rows:
        active_join_counts.update(row["join_vector"])
        sql = (active_root / row["path"]).read_text(encoding="utf-8")
        validate_semantic_query(sql, row)
        if hashlib.sha256(sql.encode("utf-8")).hexdigest() != row["content_sha256"]:
            raise RuntimeError(f"{row['path']}: output content hash mismatch")
        if sql_join_kind_counts(sql) != Counter(row["join_vector"]):
            raise RuntimeError(f"{row['path']}: SQL and benchmark join labels differ")
        if (
            row["provenance_class"] == "benchmark_source_derived"
            and row["source_benchmark"] not in SOURCE_BENCHMARKS
        ):
            raise RuntimeError(f"{row['path']}: invalid source benchmark provenance")
    if max(active_join_counts.values()) - min(active_join_counts.values()) > 1:
        raise RuntimeError(f"v2 benchmark join labels are imbalanced: {active_join_counts}")

    regression_root = root / "job_regressions"
    with (regression_root / "manifest.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        regression_rows = list(csv.DictReader(handle))
    regression_paths = {
        str(path.relative_to(regression_root))
        for path in regression_root.glob("*/*.sql")
    }
    if len(regression_rows) != V2_JOB_REGRESSION_COUNT or {
        row["path"] for row in regression_rows
    } != regression_paths:
        raise RuntimeError("v2 JOB regression manifest does not match generated SQL")
    if any(row["headline_eligible"] != "false" for row in regression_rows):
        raise RuntimeError("focused regression copies must not be counted as new samples")
    if any(
        len(set(row["join_vector"])) < 2
        or row["measurement_status"] != "requires_v2_remeasurement"
        for row in regression_rows
    ):
        raise RuntimeError("v2 JOB counterparts must be mixed and marked for remeasurement")


def validate_v3_generated(root: Path) -> None:
    """Validate v3 membership, provenance, aggregation forms, and join balance."""
    with (root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        core_rows = list(csv.DictReader(handle))
    active_root = root / "benchmark"
    with (active_root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        active_rows = list(csv.DictReader(handle))
    active_paths = {
        str(path.relative_to(active_root)) for path in active_root.glob("*/*.sql")
    }
    if len(core_rows) != V3_BENCHMARK_QUERY_COUNT:
        raise RuntimeError(f"unexpected v3 core count: {len(core_rows)}")
    if len(active_rows) != V3_BENCHMARK_QUERY_COUNT or {
        row["path"] for row in active_rows
    } != active_paths:
        raise RuntimeError("v3 benchmark manifest does not match generated SQL")
    aggregate_counts = Counter(row["aggregate_variant"] for row in core_rows)
    if aggregate_counts != Counter(V3_AGGREGATE_TARGET_COUNTS):
        raise RuntimeError(f"v3 aggregate targets changed: {aggregate_counts}")
    if Counter(row["source_benchmark"] for row in core_rows) != Counter(
        {"TPC-H": 15, "TPC-DS": 21, "JOB": 30, "SQLStorm": 36}
    ):
        raise RuntimeError("v3 source-benchmark distribution changed")
    if Counter(row["family"] for row in core_rows) != Counter(
        {"tpch": 27, "tpcds": 33, "job": 42}
    ):
        raise RuntimeError("v3 execution-family distribution changed")
    for tree_shape in {row["tree_shape"] for row in core_rows}:
        aggregate_counts = Counter(
            row["aggregate_variant"]
            for row in core_rows
            if row["tree_shape"] == tree_shape
        )
        shape_count = sum(aggregate_counts.values())
        for variant, target in V3_AGGREGATE_TARGET_COUNTS.items():
            expected = shape_count * target / V3_BENCHMARK_QUERY_COUNT
            if abs(aggregate_counts[variant] - expected) > 1.0:
                raise RuntimeError(
                    f"v3 aggregate form {variant} is confounded with {tree_shape}: "
                    f"actual={aggregate_counts[variant]}, expected={expected:.2f}"
                )
    seed_counts = Counter(row["source_location"] for row in core_rows)
    if len(seed_counts) != len(SEEDS) or set(seed_counts.values()) != {
        V3_VARIANTS_PER_SEED
    }:
        raise RuntimeError("v3 does not contain exactly three aggregate queries per seed")
    join_counts: Counter[str] = Counter()
    for row in active_rows:
        if len(set(row["join_vector"])) < 2:
            raise RuntimeError(f"{row['path']}: v3 contains a single-kind join vector")
        sql = (active_root / row["path"]).read_text(encoding="utf-8")
        validate_semantic_query(sql, row)
        if hashlib.sha256(sql.encode("utf-8")).hexdigest() != row["content_sha256"]:
            raise RuntimeError(f"{row['path']}: output content hash mismatch")
        if sql_join_kind_counts(sql) != Counter(row["join_vector"]):
            raise RuntimeError(f"{row['path']}: SQL and benchmark join labels differ")
        aggregate_token = {
            "global_count": "COUNT(",
            "grouped_min": "MIN(",
            "grouped_max": "MAX(",
            "grouped_sum": "SUM(",
        }[row["aggregate_variant"]]
        if aggregate_token not in sql.upper():
            raise RuntimeError(f"{row['path']}: missing expected root aggregation")
        grouped = row["aggregate_variant"] != "global_count"
        if ("GROUP BY" in sql.upper()) != grouped:
            raise RuntimeError(f"{row['path']}: unexpected GROUP BY form")
        join_counts.update(row["join_vector"])
    if max(join_counts.values()) - min(join_counts.values()) > 1:
        raise RuntimeError(f"v3 benchmark join labels are imbalanced: {join_counts}")

    stress_root = root / "selectivity_stress"
    with (stress_root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        stress_rows = list(csv.DictReader(handle))
    stress_paths = {
        str(path.relative_to(stress_root)) for path in stress_root.glob("*/*.sql")
    }
    if len(stress_rows) != V3_STRESS_QUERY_COUNT or {
        row["path"] for row in stress_rows
    } != stress_paths:
        raise RuntimeError("v3 selectivity-stress manifest does not match generated SQL")
    if any(
        row["corpus_version"] != "v3"
        or row["headline_eligible"] != "false"
        or row["performance_selected"] != "false"
        for row in stress_rows
    ):
        raise RuntimeError("v3 selectivity-stress must be an unselected diagnostic scope")
    stress_base_counts = Counter(row["base_query_id"] for row in stress_rows)
    if (
        len(stress_base_counts) != V3_STRESS_BASE_COUNT
        or set(stress_base_counts.values()) != {len(SELECTIVITY_STRESS_TIERS)}
    ):
        raise RuntimeError("every v3 selectivity-stress base must have all tiers")
    family_counts = Counter(row["family"] for row in stress_rows)
    expected_family_count = V3_STRESS_BASES_PER_FAMILY * len(SELECTIVITY_STRESS_TIERS)
    if family_counts != Counter(
        {family: expected_family_count for family in SELECTIVITY_STRESS_FAMILIES}
    ):
        raise RuntimeError(f"unexpected v3 selectivity-stress family balance: {family_counts}")
    base_rows = {row["base_query_id"]: row for row in stress_rows}
    if Counter(row["tree_shape"] for row in base_rows.values()) != Counter(
        {shape: 2 for shape in SELECTIVITY_STRESS_TREE_SHAPES}
    ):
        raise RuntimeError("v3 selectivity-stress base shapes are not balanced")
    if any(
        len(set(row["join_vector"])) < 2
        or int(row["relation_count"]) < SELECTIVITY_STRESS_MIN_RELATIONS
        or row["predicate_class"] != "null_rejecting_outeryan_applicable"
        for row in stress_rows
    ):
        raise RuntimeError("v3 selectivity-stress base is outside the static target domain")
    for row in stress_rows:
        sql = (stress_root / row["path"]).read_text(encoding="utf-8")
        validate_semantic_query(sql, row)
        predicate = row["selectivity_predicate"]
        if (
            predicate not in sql
            or "workload_role: metadata-selected" not in sql
            or "-- corpus_version: v3" not in sql
            or "-- derived_from_corpus_version: v2" not in sql
        ):
            raise RuntimeError(f"{row['path']}: missing selectivity-stress provenance")


def archive_versioned_corpus(root: Path) -> None:
    """Move the pre-merge definitions once; result CSVs remain immutable."""
    manifest = root / "benchmark" / "manifest.csv"
    if not manifest.exists() or "sql_fingerprint" in read_manifest(manifest)[0]:
        return
    archive = root / "revisions" / ARCHIVE_NAME
    names = ("benchmark", "core", "industry_inspired", "supplemental", "v2", "v3", "manifest.csv")
    # Check every destination before moving anything.
    for name in names:
        if (root / name).exists() and (archive / name).exists():
            raise FileExistsError(f"Refusing to overwrite historical definitions: {archive / name}")
    archive.mkdir(parents=True, exist_ok=True)
    for name in names:
        if (root / name).exists():
            shutil.move(str(root / name), str(archive / name))


def generate_unified(root: Path) -> int:
    """Build source variants privately, then emit each SQL identity exactly once."""
    previous = root / "benchmark" / "manifest.csv"
    managed = read_manifest(previous) if previous.is_file() else []
    if managed and "sql_fingerprint" in managed[0]:
        validate_unified(root / "benchmark")
    with tempfile.TemporaryDirectory(prefix="outeryan-corpus-") as directory:
        scratch = Path(directory)
        first, sweep, aggregate = (scratch / name for name in ("base", "sweep", "aggregate"))
        for path in (first, sweep, aggregate):
            path.mkdir()
        regenerate_legacy_sources()
        generate_core(first)
        generate_industry_inspired(first)
        generate_active_benchmark(first)
        generate_v2_core(sweep)
        generate_v2_benchmark(sweep, first)
        generate_v2_job_regressions(sweep, first)
        generate_v3_core(aggregate)
        generate_v3_benchmark(aggregate)
        generate_v3_selectivity_stress(aggregate, sweep, first)
        scopes = (
            ("v2", sweep / "benchmark"), ("v1", first / "benchmark"),
            ("v3_aggregation", aggregate / "benchmark"),
            ("v3_selectivity_stress", aggregate / "selectivity_stress"),
            ("v2_job_regressions", sweep / "job_regressions"),
        )
        groups = {}
        for category, source_root in scopes:
            for row in read_manifest(source_root / "manifest.csv"):
                sql = (source_root / row["path"]).read_text(encoding="utf-8")
                fingerprint = sql_fingerprint(sql, row["family"])
                if category == "v2_job_regressions":
                    if fingerprint not in groups:
                        raise ValueError("Regression guard is not present in the main corpus")
                else:
                    validate_semantic_query(sql, row)
                groups.setdefault(fingerprint, []).append((category, row, sql))

        output = scratch / "unified"
        output.mkdir()
        records, aliases, names = [], [], set()
        for fingerprint, members in groups.items():
            _, source, sql = members[0]
            query_id = canonical_query_id(source)
            if query_id in names:
                query_id += "__" + fingerprint[:10]
            if query_id in names:
                raise RuntimeError(f"Canonical query name collision: {query_id}")
            names.add(query_id)
            category = query_id.split("__", 1)[0]
            relative = f"{source['family']}/{query_id}.sql"
            body = "\n".join(line for line in sql.splitlines()
                             if not line.lstrip().startswith("--")).strip() + "\n"
            content = (f"-- query_type: {category}; family: {source['family']}\n"
                       + f"-- source: {source.get('source_benchmark', '')} {source.get('source_query', '')}".rstrip() + "\n"
                       + semantic_comment(source) + body)
            destination = output / relative
            destination.parent.mkdir(exist_ok=True)
            destination.write_text(content, encoding="utf-8")
            stress = any(item[0] == "v3_selectivity_stress" for item in members)
            regression = any(item[0] == "v2_job_regressions" for item in members)
            record = {key: value for key, value in source.items() if key not in (
                "query_id", "path", "corpus_version", "source_path", "source_content_sha256",
                "base_query_id", "pattern_role", "corpus_revision")}
            record.update(
                query_id=query_id, path=relative, query_class=category, workload_category=category,
                corpus_revision="unique-semantic-20260929", sql_fingerprint=fingerprint,
                content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                source_component="core" if category in ("join", "aggregate") else "evaluation",
                evaluation_role="benchmark_derived" if category == "join" else
                                "benchmark_aggregate" if category == "aggregate" else source["evaluation_role"],
                selectivity_stress="true" if stress else "false",
                regression_guard="true" if regression else "false",
            )
            records.append(record)
            for old_category, old, _ in members:
                aliases.append(dict(
                    workload_category=old_category, query_id=old["query_id"], family=old["family"],
                    sql_path=old["path"], content_sha256=old["content_sha256"],
                    canonical_query_id=query_id, canonical_path=relative,
                    canonical_category=category, sql_fingerprint=fingerprint,
                ))
        records.sort(key=lambda row: row["path"])
        fields = list(dict.fromkeys(key for row in records for key in row))
        with (output / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(records)
        with (output / "aliases.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(aliases[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(sorted(aliases, key=lambda row: (row["workload_category"], row["query_id"])))
        for flag, filename in (("selectivity_stress", "selectivity_stress.txt"),
                               ("regression_guard", "job_regressions.txt")):
            (output / filename).write_text("".join(row["path"] + "\n" for row in records
                                                   if row[flag] == "true"), encoding="utf-8")
        validate_unified(output)
        root.mkdir(parents=True, exist_ok=True)
        archive_versioned_corpus(root)
        if managed and "sql_fingerprint" in managed[0]:
            retained = {row["path"] for row in records}
            for row in managed:
                if row["path"] not in retained:
                    (root / "benchmark" / row["path"]).unlink()
        for source in output.rglob("*"):
            if source.is_file():
                destination = root / "benchmark" / source.relative_to(output)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
    counts = Counter(row["query_class"] for row in records)
    print(f"Generated {len(records)} unique queries: {dict(counts)}; {len(aliases)} historical aliases")
    return len(records)


def validate_unified(benchmark: Path) -> None:
    rows = read_manifest(benchmark / "manifest.csv")
    fingerprints = set()
    for row in rows:
        sql = (benchmark / row["path"]).read_text(encoding="utf-8")
        validate_semantic_query(sql, row)
        fingerprint = sql_fingerprint(sql, row["family"])
        if fingerprint != row["sql_fingerprint"] or fingerprint in fingerprints:
            raise ValueError(f"Duplicate or incorrect SQL identity: {row['path']}")
        fingerprints.add(fingerprint)
        if re.search(r"(?:^|_)v\d+(?:_|$)", row["query_id"]):
            raise ValueError(f"Version in canonical query name: {row['query_id']}")
        if hashlib.sha256(sql.encode()).hexdigest() != row["content_sha256"]:
            raise ValueError(f"SQL hash mismatch: {row['path']}")
    if {row["path"] for row in rows} != {str(path.relative_to(benchmark)) for path in benchmark.glob("*/*.sql")}:
        raise ValueError("Unified manifest does not match SQL files")
    identities = {row["query_id"]: row for row in rows}
    for alias in read_manifest(benchmark / "aliases.csv"):
        if identities[alias["canonical_query_id"]]["sql_fingerprint"] != alias["sql_fingerprint"]:
            raise ValueError("Historical alias changed SQL identity")


def audit_selectivity(root: Path, binary: Path, output: Path, timeout: int) -> bool:
    """Recount frozen cohorts on a target scale without executing workload queries."""
    used: dict[str, set[str]] = {}
    manifests = {}
    distributions = {}
    for scope in ("benchmark",):
        path = root / scope / "manifest.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        manifests[scope] = hashlib.sha256(path.read_bytes()).hexdigest()
        distributions[scope] = dict(Counter(row["semantic_tier"] for row in rows))
        for row in rows:
            if row["filter_design_revision"] != V1_CORPUS_REVISION:
                raise ValueError(f"Regenerate {scope} before auditing the semantic revision")
            used.setdefault(row["selectivity_profile"], set()).add(row["semantic_tier"])

    report_rows = []
    for profile_id, tiers in sorted(used.items()):
        profile = SEMANTIC_DESIGN["profiles"][profile_id]
        family = profile["family"]
        database = database_path(family, REPO_ROOT).resolve()
        if not database.is_file():
            raise FileNotFoundError(f"Set {family.upper()}_DB to an existing database: {database}")
        ordered = [tier for tier in SEMANTIC_TIERS if tier in tiers]
        predicates = [semantic_filter(profile_id, profile["column"], tier) for tier in ordered]
        aggregates = ["COUNT(*) AS n"] + [
            f"COUNT(*) FILTER (WHERE {predicate}) AS c{index}"
            for index, predicate in enumerate(predicates)
        ]
        sql = ("SET disabled_optimizers='outer_yan'; SET threads=4; SELECT "
               + ", ".join(aggregates) + " FROM " + profile["calibration_from"] + ";")
        result = subprocess.run(
            [str(binary), "-readonly", "-no-init", "-bail", "-json", str(database), "-c", sql],
            capture_output=True, text=True, timeout=timeout, check=True,
        )
        counts = json.loads(result.stdout)[0]
        for index, (tier, predicate) in enumerate(zip(ordered, predicates)):
            metadata = semantic_metadata(profile_id, profile["column"], tier)
            fraction = counts[f"c{index}"] / counts["n"] if counts["n"] else 0.0
            spec = SEMANTIC_DESIGN["tiers"][SEMANTIC_TIERS.index(tier)]
            in_range = fraction_in_band(fraction, spec)
            report_rows.append({
                "profile": profile_id, "family": family, "tier": tier,
                "database": str(database), "predicate": predicate,
                "denominator": profile["calibration_from"], "total_rows": counts["n"],
                "qualified_rows": counts[f"c{index}"], "observed_fraction": fraction,
                "frozen_calibration_fraction": float(metadata["calibration_fraction"]),
                "target_min_fraction": float(metadata["target_min_fraction"]),
                "target_max_fraction": float(metadata["target_max_fraction"]),
                "include_lower": spec["include_lower"], "include_upper": spec["include_upper"],
                "in_range": in_range,
            })
        failed = [row["tier"] for row in report_rows if row["profile"] == profile_id and not row["in_range"]]
        print(f"{profile_id}: {counts['n']} base rows; "
              + (f"OUT OF RANGE: {', '.join(failed)}" if failed else "all used bands verified"), flush=True)
    success = all(row["in_range"] for row in report_rows)
    report = {
        "revision": V1_CORPUS_REVISION, "all_used_bands_in_range": success,
        "scope": "base-entity filter fractions, not joined output or cost-model estimates",
        "manifest_sha256": manifests, "query_distribution": distributions, "profiles": report_rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Selectivity audit: {len(report_rows)} profile/band pairs; report: {output}")
    return success


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", help=argparse.SUPPRESS)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--batch", type=int, default=0, help="Disjoint candidate batch (default: 0)")
    parser.add_argument("--per-family", type=int, default=180)
    parser.add_argument("--core-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--audit-selectivity", action="store_true",
                        help="count base-entity cohorts on existing databases; do not regenerate or run workload SQL")
    parser.add_argument("--audit-output", type=Path,
                        default=SCRIPT_DIR / "results" / "semantic_selectivity_audit.json")
    parser.add_argument("--duckdb", type=Path,
                        default=Path(os.environ.get("DUCKDB_BIN", REPO_ROOT / "build/release/duckdb")))
    parser.add_argument("--audit-timeout", type=int, default=120,
                        help="per-profile count timeout in seconds (default: 120)")
    args = parser.parse_args()

    if args.audit_selectivity:
        if args.audit_timeout <= 0:
            parser.error("--audit-timeout must be positive")
        from qualify_benchmark import audit_selectivity as audit_balanced
        if not audit_balanced(args.root or DEFAULT_ROOT, args.duckdb.resolve(),
                                 args.audit_output, args.audit_timeout):
            raise SystemExit(1)
        return

    if args.version or args.core_only:
        parser.error("Versioned generation is retired; run without --version/--core-only for the unique corpus")
    from balanced_benchmark import generate
    generate(args.root or DEFAULT_ROOT, args.per_family, args.batch)


if __name__ == "__main__":
    main()
