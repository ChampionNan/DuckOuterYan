#!/usr/bin/env python3
"""Generate the provenance-backed OuterJoin benchmark corpus.

The generated core is independent of OuterYan performance results.  Each seed
records an upstream benchmark query and retains a connected subgraph of its
relation instances and join predicates.  The SQL is normalized to a flat
projection/filter/join skeleton so that it remains inside the optimizer's
current applicability envelope.

The active ``benchmark`` corpus is the union used by the harness. Query names
use only two reporting prefixes: ``derived__`` for generated/legacy synthetic
queries and ``industry__`` for business-role patterns. The manifest preserves
the more specific evaluation role, including whether a query was retained as
a pinned legacy performance guard.

The ``core``, ``industry_inspired``, and ``supplemental`` directories remain as
auditable component views of that one active benchmark.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import re
import shutil
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

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
LEGACY_ROOT = SCRIPT_DIR / "outerjoin_query_old"
TIMEOUT_ROOT = SCRIPT_DIR / "outerjoin_query_timeout"
CORE_QUERY_COUNT = 170
INDUSTRY_EVALUATION_QUERY_COUNT = 36
ACTIVE_BENCHMARK_QUERY_COUNT = CORE_QUERY_COUNT + INDUSTRY_EVALUATION_QUERY_COUNT
LEGACY_WIN_SELECTION_POLICY = (
    f"{REFERENCE_RUN}: correct=TRUE; "
    "selected_plan=OUTERYAN; tm_speedup>1.0"
)
ACTIVE_LEGACY_SOURCE_SELECTION_POLICY = (
    LEGACY_WIN_SELECTION_POLICY + "; archived source query before active normalization"
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
    where: str
    semantic_vector: tuple[str, ...]

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
    where: str,
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
        where=where,
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
            where=where,
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
        for alias, relation in zip(aliases, relations):
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

    anchor = included[0]
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
        where=f"{anchor}.id % 1000 = 0",
        offset=offset,
    )


def sqlstorm_seed(
    dataset: str,
    query_id: str,
    *,
    anchor_filter: str,
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
                "the anchor sample is enriched under controlled preservation semantics."
            ),
            relations=relations,
            predicates=predicates,
            where=anchor_filter,
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
            "the anchor sample is enriched under controlled preservation semantics."
        ),
        relations=relations,
        predicates=predicates,
        where=anchor_filter,
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
        where=(
            "r.r_name = 'ASIA' "
            "AND o.o_orderdate >= DATE '1994-01-01' "
            "AND o.o_orderdate < DATE '1995-01-01'"
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
        where="p.p_name LIKE '%green%'",
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
        where="cs.cs_order_number % 1000 = 0",
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
        where="cs.cs_order_number % 1000 = 0",
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
        topology="branch",
        semantics=(
            "Movie-credit coverage: qualifying titles retain cast records while "
            "character, role, and company annotations may be absent."
        ),
        relations=("title t", "cast_info ci", "char_name chn", "role_type rt", "movie_companies mc"),
        predicates=(
            "t.id = ci.movie_id",
            "chn.id = ci.person_role_id",
            "rt.id = ci.role_id",
            "t.id = mc.movie_id",
        ),
        projection=(
            "t.id AS title_id, t.title, ci.person_id, chn.name AS character_name, "
            "rt.role, mc.company_id"
        ),
        where="t.production_year > 2005",
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
        where="t.id % 1000 = 0",
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
        where="p.p_partkey <= 1000",
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
        where="c.c_customer_sk % 1000 = 0",
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
        where="ci.id % 1000 = 0",
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
        where="c.c_custkey % 1000 = 0",
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
        where="s.s_suppkey % 100 = 0",
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
        where="p.p_partkey % 1000 = 0",
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
        where="wr.wr_order_number % 1000 = 0",
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
        where="ss.ss_ticket_number % 1000 = 0",
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
        where="ss.ss_ticket_number % 1000 = 0",
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
        where="ws.ws_order_number % 1000 = 0",
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
        where="ss.ss_ticket_number % 1000 = 0",
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
        anchor_filter="p.p_partkey % 1000 = 0", offset=1,
    ),
    sqlstorm_seed(
        "tpch", "25509",
        anchor_filter="p.p_partkey % 1000 = 0", offset=2,
    ),
    sqlstorm_seed(
        "tpch", "15031",
        anchor_filter="p.p_partkey % 1000 = 0", offset=3,
    ),
    sqlstorm_seed(
        "tpcds", "11376",
        anchor_filter="c.c_customer_sk % 1000 = 0", offset=1,
    ),
    sqlstorm_seed(
        "tpcds", "28643",
        anchor_filter="C.c_customer_sk % 1000 = 0", offset=2,
    ),
    sqlstorm_seed(
        "tpcds", "14368",
        anchor_filter="c.c_customer_sk % 1000 = 0", offset=3,
    ),
    sqlstorm_seed(
        "job", "11914",
        anchor_filter="a.id % 1000 = 0", offset=1,
    ),
    sqlstorm_seed(
        "job", "18930",
        anchor_filter="a.id % 1000 = 0", offset=2,
    ),
    sqlstorm_seed(
        "job", "13193",
        anchor_filter="c.id % 1000 = 0", offset=3,
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


def build_alternate_deep(seed: Seed, *, right_deep: bool) -> str:
    """Build a second cross-product-free deep traversal from the last relation."""
    return build_connected_deep(
        seed,
        right_deep=right_deep,
        start_index=len(seed.relations) - 1,
        prefer_max_edge=True,
    )


def build_connected_deep(
    seed: Seed,
    *,
    right_deep: bool,
    start_index: int,
    prefer_max_edge: bool,
) -> str:
    """Build a connected all-FULL traversal from a selected relation."""
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
            expression = f"({relation} {ACTIVE_JOIN_SQL} {expression} ON {predicate})"
        else:
            expression = f"({expression} {ACTIVE_JOIN_SQL} {relation} ON {predicate})"
        visited.add(new_alias)
    return expression


def build_secondary_right_deep(seed: Seed) -> str:
    """Build a third syntactically distinct connected right-deep FULL tree."""
    full_vector = ("F",) * len(seed.predicates)
    existing = {
        build_right_mirror(seed, full_vector),
        build_alternate_deep(seed, right_deep=True),
    }
    middle = len(seed.relations) // 2
    start_order = [middle, *range(len(seed.relations))]
    for start_index in dict.fromkeys(start_order):
        for prefer_max_edge in (False, True):
            candidate = build_connected_deep(
                seed,
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
    """Return one plain, type-compatible equality for the same graph edge."""
    match = SIMPLE_EDGE_EQUALITY.search(predicate)
    if not match:
        raise ValueError(f"join edge has no plain qualified equality: {predicate}")
    equality = match.group(0)
    # The local JOB load infers person_role_id as DOUBLE while char_name.id is
    # INTEGER. Using ci.role_id keeps this graph edge column-to-column and
    # avoids the implicit cast that is outside OuterYan's current envelope.
    if equality == "chn.id = ci.person_role_id":
        return "chn.id = ci.role_id"
    return equality


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
    if alternate and any(kind != "F" for kind in kinds):
        raise ValueError("alternate bushy orientation currently requires all-FULL joins")
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
        f"-- business_semantics: {seed.semantics}\n"
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
        for suffix, vector, tree_shape, variant_semantics, sql in variant_rows(seed, seed_index):
            query_id = f"ojb_{seed.seed_id}_{suffix}"
            relative_path = f"{seed.family}/{query_id}.sql"
            expected_graph = Counter(
                tuple(sorted(predicate_aliases(predicate))) for predicate in seed.predicates
            )
            if sql_join_graph(sql) != expected_graph:
                raise RuntimeError(f"{query_id}: emitted SQL changed the seed join graph")
            (core / relative_path).write_text(sql, encoding="utf-8")
            manifest_rows.append(
                {
                    "query_id": query_id,
                    "path": relative_path,
                    "stratum": "benchmark_derived_core",
                    "family": seed.family,
                    "source_benchmark": seed.source_benchmark,
                    "source_version": seed.source_version,
                    "source_query": seed.source_query,
                    "source_location": seed.source_location,
                    "source_sha256": seed.source_hash,
                    "transformation": "connected_join_subgraph_adaptation",
                    "topology": seed.topology,
                    "tree_shape": tree_shape,
                    "join_vector": vector,
                    "relation_count": str(len(seed.relations)),
                    "predicate_class": "null_rejecting_outeryan_applicable",
                    "semantic_role": variant_semantics,
                    "semantics": seed.semantics,
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
    """Materialize graph-preserving, OuterYan-applicable evaluation queries."""
    destination_root = root / "industry_inspired"
    reset_generated_dir(destination_root)
    rows: list[dict[str, str]] = []
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
        normalized_sql = normalize_active_sql(
            source.read_text(encoding="utf-8"),
            flatten_aggregate=(family, filename) in ACTIVE_AGGREGATE_SOURCES,
        )
        destination.write_text(normalized_sql, encoding="utf-8")
        observed_speedup = wins.get((family, filename), "")
        rows.append(
            {
                "query_id": source.stem,
                "path": f"{family}/{filename}",
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
                "observed_tm_speedup": observed_speedup,
                "active_transformation": "graph_preserving_outeryan_applicability_normalization",
                "content_sha256": hashlib.sha256(normalized_sql.encode("utf-8")).hexdigest(),
            }
        )

    for family, filename, speedup in LEGACY_OUTERYAN_WINS:
        if (family, filename) in pattern_keys:
            continue
        source = LEGACY_ROOT / family / filename
        if not source.is_file():
            raise FileNotFoundError(f"legacy performance-win query not found: {source}")
        destination = destination_root / family / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        normalized_sql = normalize_active_sql(source.read_text(encoding="utf-8"))
        destination.write_text(normalized_sql, encoding="utf-8")
        rows.append(
            {
                "query_id": source.stem,
                "path": f"{family}/{filename}",
                "evaluation_role": "legacy_performance_win",
                "stratum": "synthetic_optimizer_stress",
                "family": family,
                "source": f"outerjoin_query_old/{family}/{filename}",
                "pattern_class": "observed_outeryan_speedup",
                "semantics": (
                    "Graph from a legacy synthetic query with a previously observed "
                    "OuterYan speedup; the active SQL is applicability-normalized."
                ),
                "industry_status": "not_industry_derived",
                "production_source_id": "none",
                "selection_policy": ACTIVE_LEGACY_SOURCE_SELECTION_POLICY,
                "observed_tm_speedup": speedup,
                "active_transformation": "graph_preserving_outeryan_applicability_normalization",
                "content_sha256": hashlib.sha256(normalized_sql.encode("utf-8")).hexdigest(),
            }
        )

    expected_paths = {
        f"{family}/{filename}" for family, filename in pattern_keys | set(wins)
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

    fields = list(rows[0])
    with (destination_root / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def generate_active_benchmark(root: Path, include_industry: bool = True) -> int:
    """Materialize the single harness corpus with provenance in query names."""
    destination_root = root / "benchmark"
    reset_generated_dir(destination_root)
    rows: list[dict[str, str]] = []

    with (root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        core_rows = list(csv.DictReader(handle))
    for row in core_rows:
        family = row["family"]
        source = root / "core" / row["path"]
        query_id = f"derived__{row['query_id']}"
        destination = destination_root / family / f"{query_id}.sql"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        rows.append(
            {
                "query_id": query_id,
                "path": f"{family}/{query_id}.sql",
                "query_class": "derived",
                "evaluation_role": "benchmark_derived",
                "family": family,
                "source_component": "core",
                "source_path": f"core/{row['path']}",
                "content_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
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
            "legacy_performance_win": ("derived", "derived"),
        }
        for row in industry_rows:
            role = row["evaluation_role"]
            if role not in role_prefix:
                raise RuntimeError(f"unknown industry evaluation role: {role}")
            prefix, query_class = role_prefix[role]
            family = row["family"]
            source = root / "industry_inspired" / row["path"]
            query_id = f"{prefix}__{row['query_id']}"
            destination = destination_root / family / f"{query_id}.sql"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            rows.append(
                {
                    "query_id": query_id,
                    "path": f"{family}/{query_id}.sql",
                    "query_class": query_class,
                    "evaluation_role": role,
                    "family": family,
                    "source_component": "industry_inspired",
                    "source_path": f"industry_inspired/{row['path']}",
                    "content_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                }
            )

    expected_count = ACTIVE_BENCHMARK_QUERY_COUNT if include_industry else CORE_QUERY_COUNT
    paths = {row["path"] for row in rows}
    if len(rows) != expected_count or len(paths) != expected_count:
        raise RuntimeError(
            "active benchmark membership mismatch: "
            f"expected={expected_count}, rows={len(rows)}, unique_paths={len(paths)}"
        )

    fields = list(rows[0])
    with (destination_root / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


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
    sources: list[tuple[Path, Path]] = []
    for query in LEGACY_QUERIES:
        source_root = TIMEOUT_ROOT if query.timed_out else LEGACY_ROOT
        source = source_root / query.path
        if not source.is_file():
            raise FileNotFoundError(f"classified legacy query not found: {source}")
        sources.append((source, source_root))
    for source, source_root in sources:
        relative = str(source.relative_to(source_root))
        family = source.parent.name
        if is_dataless(source):
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

    for row in manifest_rows:
        suffix = row["query_id"].rsplit("_", 1)[-1]
        expected_vector = "F" * (int(row["relation_count"]) - 1)
        if suffix != "alt" and row["join_vector"] != expected_vector:
            raise RuntimeError(
                f"{row['query_id']}: active join vector must be {expected_vector}, "
                f"got {row['join_vector']}"
            )
        if suffix == "alt" and set(row["join_vector"]) == {"I"}:
            raise RuntimeError(f"{row['query_id']}: alternate vector has no outer join")
    all_shapes = Counter(row["tree_shape"] for row in manifest_rows)
    if all_shapes != Counter({"left_deep": 46, "right_deep": 80, "bushy": 44}):
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
        if not relative_path.endswith("_alt.sql") and any(
            token in statement for token in (" INNER JOIN", " LEFT OUTER JOIN", " RIGHT OUTER JOIN")
        ):
            raise RuntimeError(f"{relative_path}: active core join is not FULL OUTER")
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

    active_root = root / "benchmark"
    with (active_root / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        active_rows = list(csv.DictReader(handle))
    active_paths = {
        str(path.relative_to(active_root)) for path in active_root.glob("*/*.sql")
    }
    expected_active_count = ACTIVE_BENCHMARK_QUERY_COUNT if include_industry else CORE_QUERY_COUNT
    if len(active_rows) != expected_active_count or {
        row["path"] for row in active_rows
    } != active_paths:
        raise RuntimeError("active benchmark manifest does not match generated SQL")
    valid_prefixes = ("derived__", "industry__")
    if any(not row["query_id"].startswith(valid_prefixes) for row in active_rows):
        raise RuntimeError("active benchmark query is missing its provenance prefix")
    for relative_path in sorted(active_paths):
        sql = (active_root / relative_path).read_text(encoding="utf-8")
        statement = "\n".join(
            line for line in sql.upper().splitlines() if not line.lstrip().startswith("--")
        )
        if any(token in statement for token in ("GROUP BY", "SELECT DISTINCT", " OVER (")):
            raise RuntimeError(f"{relative_path}: active query bypasses OuterYan")
        if "derived__ojb_" not in relative_path and any(
            token in statement for token in (" INNER JOIN", " LEFT OUTER JOIN", " RIGHT OUTER JOIN")
        ):
            raise RuntimeError(f"{relative_path}: active join is not FULL OUTER")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--core-only", action="store_true")
    args = parser.parse_args()

    args.root.mkdir(parents=True, exist_ok=True)
    core_count = generate_core(args.root)
    if not args.core_only:
        regenerate_legacy_sources()
    supplemental_count = 0 if args.core_only else generate_supplemental(args.root)
    industry_count = 0 if args.core_only else generate_industry_inspired(args.root)
    benchmark_count = generate_active_benchmark(args.root, include_industry=not args.core_only)
    timeout_count = generate_timeout_manifest(args.root)
    legacy_count = classify_legacy(args.root)
    validate_generated(args.root, include_industry=not args.core_only)
    print(
        f"generated {benchmark_count} active benchmark, {core_count} derived core, "
        f"{industry_count} industry-evaluation, and {supplemental_count} supplemental queries; "
        f"excluded {timeout_count} timeouts and classified {legacy_count} legacy queries "
        f"under {args.root}"
    )


if __name__ == "__main__":
    main()
