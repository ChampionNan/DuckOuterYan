#!/usr/bin/env python3
"""Generate the provenance-backed OuterJoin benchmark corpus.

The generated core is independent of OuterYan performance results.  Each seed
records an upstream benchmark query and retains a connected subgraph of its
relation instances and join predicates.  The SQL is normalized to a flat
projection/filter/join skeleton so that it remains inside the optimizer's
current applicability envelope.

The supplemental corpus is deliberately separate.  It contains legacy stress
queries that were useful during OuterYan development, but it is not part of the
benchmark-derived core and must not be described as industry-derived.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_ROOT = SCRIPT_DIR / "outerjoin_benchmark"
LEGACY_ROOT = SCRIPT_DIR / "outerjoin_query_old"
TIMEOUT_ROOT = SCRIPT_DIR / "outerjoin_query_timeout"
REFERENCE_RESULT = SCRIPT_DIR / "results" / "experiment_onoff_20260810_084908.csv"
REFERENCE_RESULT_SHA256 = "b27bbde2ca0e5ca2a63df07a62637220765ef48042eaca7ca4110fcecae5a4bb"
REFERENCE_ROW_COUNT = 254
REFERENCE_TIMEOUT_COUNT = 84
CORE_QUERY_COUNT = REFERENCE_ROW_COUNT - REFERENCE_TIMEOUT_COUNT

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
        "completeness_aggregation",
        "Customer activity is aggregated while retaining customers without order lines.",
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
        "dimension_coverage_aggregation",
        "Store activity is aggregated while optional item, store, and customer dimensions are retained.",
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


def file_sha256(relative_path: str) -> str:
    return hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest()


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


def job_seed(query_id: str, *, max_relations: int = 5, offset: int = 0) -> Seed:
    source_location = f"benchmark/imdb_plan_cost/queries/{query_id}.sql"
    text = (REPO_ROOT / source_location).read_text(encoding="utf-8")
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
        where=f"({anchor}.id % 1000 = 0 OR {anchor}.id IS NULL)",
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
    text = (REPO_ROOT / source_location).read_text(encoding="utf-8")
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
            "Regional sales in the source date window: retain NULL-aware region "
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
            "(r.r_name = 'ASIA' OR r.r_regionkey IS NULL) "
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
        where="(p.p_name LIKE '%green%' OR p.p_partkey IS NULL)",
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
        where="(cs.cs_order_number % 1000 = 0 OR cs.cs_order_number IS NULL)",
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
        where="(cs.cs_order_number % 1000 = 0 OR cs.cs_order_number IS NULL)",
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
        where="(t.production_year > 2005 OR t.id IS NULL)",
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
        where="(t.id % 1000 = 0 OR t.id IS NULL)",
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
        where="(p.p_partkey <= 1000 OR p.p_partkey IS NULL)",
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
        where="(c.c_customer_sk % 1000 = 0 OR c.c_customer_sk IS NULL)",
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
        where="(ci.id % 1000 = 0 OR ci.id IS NULL)",
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
        where="(c.c_custkey % 1000 = 0 OR c.c_custkey IS NULL)",
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
        where="(s.s_suppkey % 100 = 0 OR s.s_suppkey IS NULL)",
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
        where="(p.p_partkey % 1000 = 0 OR p.p_partkey IS NULL)",
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
        where="(wr.wr_order_number % 1000 = 0 OR wr.wr_order_number IS NULL)",
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
        where="(ss.ss_ticket_number % 1000 = 0 OR ss.ss_ticket_number IS NULL)",
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
        where="(ss.ss_ticket_number % 1000 = 0 OR ss.ss_ticket_number IS NULL)",
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
        where="(ws.ws_order_number % 1000 = 0 OR ws.ws_order_number IS NULL)",
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
        where="(ss.ss_ticket_number % 1000 = 0 OR ss.ss_ticket_number IS NULL)",
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
        anchor_filter="(p.p_partkey % 1000 = 0 OR p.p_partkey IS NULL)", offset=1,
    ),
    sqlstorm_seed(
        "tpch", "25509",
        anchor_filter="(p.p_partkey % 1000 = 0 OR p.p_partkey IS NULL)", offset=2,
    ),
    sqlstorm_seed(
        "tpch", "15031",
        anchor_filter="(p.p_partkey % 1000 = 0 OR p.p_partkey IS NULL)", offset=3,
    ),
    sqlstorm_seed(
        "tpcds", "11376",
        anchor_filter="(c.c_customer_sk % 1000 = 0 OR c.c_customer_sk IS NULL)", offset=1,
    ),
    sqlstorm_seed(
        "tpcds", "28643",
        anchor_filter="(C.c_customer_sk % 1000 = 0 OR C.c_customer_sk IS NULL)", offset=2,
    ),
    sqlstorm_seed(
        "tpcds", "14368",
        anchor_filter="(c.c_customer_sk % 1000 = 0 OR c.c_customer_sk IS NULL)", offset=3,
    ),
    sqlstorm_seed(
        "job", "11914",
        anchor_filter="(a.id % 1000 = 0 OR a.id IS NULL)", offset=1,
    ),
    sqlstorm_seed(
        "job", "18930",
        anchor_filter="(a.id % 1000 = 0 OR a.id IS NULL)", offset=2,
    ),
    sqlstorm_seed(
        "job", "13193",
        anchor_filter="(c.id % 1000 = 0 OR c.id IS NULL)", offset=3,
    ),
)

SEEDS = SEEDS + ADDITIONAL_SEEDS


# The reference run calibrates corpus size and identifies a separate diagnostic
# suite.  It never determines membership in the benchmark-derived core.
def load_reference_rows() -> list[dict[str, str]]:
    actual_hash = hashlib.sha256(REFERENCE_RESULT.read_bytes()).hexdigest()
    if actual_hash != REFERENCE_RESULT_SHA256:
        raise RuntimeError(
            f"reference result changed: expected {REFERENCE_RESULT_SHA256}, got {actual_hash}"
        )
    with REFERENCE_RESULT.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    timeout_count = sum(row["note"] == "TIMEOUT" for row in rows)
    completed_count = sum(row["correct"] == "TRUE" for row in rows)
    if (
        len(rows) != REFERENCE_ROW_COUNT
        or timeout_count != REFERENCE_TIMEOUT_COUNT
        or completed_count != CORE_QUERY_COUNT
    ):
        raise RuntimeError(
            "unexpected reference-result population: "
            f"rows={len(rows)}, timeouts={timeout_count}, completed={completed_count}"
        )
    return rows


def supplemental_stress() -> tuple[tuple[str, str, str], ...]:
    """Return correct, selected OuterYan wins from the pinned reference run."""
    selected: list[tuple[str, str, str]] = []
    for row in load_reference_rows():
        speedup = row["tm_speedup"]
        if (
            row["correct"] == "TRUE"
            and row["selected_plan"] == "OUTERYAN"
            and speedup not in ("", "-")
            and float(speedup) >= 1.20
        ):
            selected.append((row["family"], Path(row["sql_path"]).name, speedup))
    return tuple(selected)


def reference_timeouts() -> set[str]:
    return {row["sql_path"] for row in load_reference_rows() if row["note"] == "TIMEOUT"}


def build_left_deep(seed: Seed, kinds: Sequence[str]) -> str:
    expression = seed.relations[0]
    for relation, predicate, kind in zip(seed.relations[1:], seed.predicates, kinds):
        expression = f"({expression} {JOIN_SQL[kind]} {relation} ON {predicate})"
    return expression


def flip_join_kind(kind: str) -> str:
    return {"I": "I", "L": "R", "R": "L", "F": "F"}[kind]


def build_right_deep(seed: Seed, kinds: Sequence[str]) -> str:
    """Build a right-deep tree whose emitted operators are given by kinds."""
    expression = seed.relations[0]
    for relation, predicate, kind in zip(seed.relations[1:], seed.predicates, kinds):
        expression = f"({relation} {JOIN_SQL[kind]} {expression} ON {predicate})"
    return expression


def build_right_mirror(seed: Seed, kinds: Sequence[str]) -> str:
    """Mirror a labeled left-deep tree into an equivalent right-deep tree."""
    return build_right_deep(seed, tuple(flip_join_kind(kind) for kind in kinds))


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


def build_bushy_mixed(seed: Seed, kinds: Sequence[str]) -> str:
    """Build a balanced connected tree without introducing cross products."""
    aliases = [relation_alias(relation) for relation in seed.relations]
    alias_order = {alias: index for index, alias in enumerate(aliases)}
    relation_by_alias = dict(zip(aliases, seed.relations))
    edges = [(*predicate_aliases(predicate), index) for index, predicate in enumerate(seed.predicates)]

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
        _, edge_index, first, second = min(candidates, key=lambda item: (item[0], item[1]))
        if min(alias_order[alias] for alias in first) > min(alias_order[alias] for alias in second):
            first, second = second, first
        return first, second, edge_index

    def build(nodes: set[str]) -> str:
        if len(nodes) == 1:
            return relation_by_alias[next(iter(nodes))]
        left_nodes, right_nodes, edge_index = split(nodes)
        return (
            f"({build(left_nodes)} {JOIN_SQL[kinds[edge_index]]} {build(right_nodes)} "
            f"ON {seed.predicates[edge_index]})"
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
    yield (
        "ldmx",
        "".join(seed.semantic_vector),
        "left_deep",
        "primary left-deep mixture of mandatory, optional, and reconciliation edges",
        query_sql(
            seed,
            build_left_deep(seed, seed.semantic_vector),
            "ldmx",
            "primary left-deep mixed join labeling",
        ),
    )
    yield (
        "rdmx",
        "".join(flip_join_kind(kind) for kind in seed.semantic_vector),
        "right_deep",
        "RIGHT-deep mirror, equivalent to the primary left-deep mixture",
        query_sql(
            seed,
            build_right_mirror(seed, seed.semantic_vector),
            "rdmx",
            "semantics-equivalent right-deep mirror of the primary mixed labeling",
        ),
    )
    if bushy_root_partition(seed) is not None:
        yield (
            "bmx",
            "".join(seed.semantic_vector),
            "bushy",
            "balanced connected bushy tree with the documented mixed labeling",
            query_sql(
                seed,
                build_bushy_mixed(seed, seed.semantic_vector),
                "bmx",
                "cross-product-free bushy grouping with mixed join labeling",
            ),
        )
    else:
        alternate = alternate_vector(seed)
        yield (
            "alt",
            "".join(alternate),
            "left_deep",
            "systematic alternate mixture for join-kind coverage",
            query_sql(
                seed,
                build_left_deep(seed, alternate),
                "alt",
                "deterministic alternate mixed labeling; bushy grouping is structurally ineligible",
            ),
        )

    # Uniform controls are distributed globally over LEFT, RIGHT, and FULL.
    # With 68 slots, the closest possible balance is 23/23/22.
    uniform_kinds = ("L", "R", "F")
    left_uniform_kind = uniform_kinds[(2 * seed_index) % len(uniform_kinds)]
    right_uniform_kind = uniform_kinds[(2 * seed_index + 1) % len(uniform_kinds)]
    left_uniform = (left_uniform_kind,) * edge_count
    right_uniform = (right_uniform_kind,) * edge_count
    yield (
        f"ldu{left_uniform_kind}",
        "".join(left_uniform),
        "left_deep",
        f"uniform left-deep {JOIN_SQL[left_uniform_kind]} control",
        query_sql(
            seed,
            build_left_deep(seed, left_uniform),
            f"ldu{left_uniform_kind}",
            f"uniform left-deep {JOIN_SQL[left_uniform_kind]} control",
        ),
    )
    yield (
        f"rdu{right_uniform_kind}",
        "".join(right_uniform),
        "right_deep",
        f"uniform right-deep {JOIN_SQL[right_uniform_kind]} control",
        query_sql(
            seed,
            build_right_deep(seed, right_uniform),
            f"rdu{right_uniform_kind}",
            f"uniform right-deep {JOIN_SQL[right_uniform_kind]} control",
        ),
    )


def reset_generated_dir(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)


def verify_source(seed: Seed) -> None:
    if seed.source_location.startswith(("http://", "https://")):
        # Remote artifacts are pinned by immutable URL and recorded hash.  The
        # generator intentionally remains usable without network access.
        return
    source = REPO_ROOT / seed.source_location
    if not source.is_file():
        raise FileNotFoundError(f"{seed.seed_id}: source query not found: {source}")
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
                    "predicate_class": (
                        "mixed_null_preserving_and_null_rejecting"
                        if seed.seed_id == "tpch_q05_region_sales"
                        else "null_preserving"
                    ),
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
    for family, filename, speedup in supplemental_stress():
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
                "selection_policy": (
                    "experiment_onoff_20260810_084908.csv: correct=TRUE; "
                    "selected_plan=OUTERYAN; tm_speedup>=1.20"
                ),
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
    """Materialize legacy business patterns as a non-production-derived stratum."""
    destination_root = root / "industry_inspired"
    reset_generated_dir(destination_root)
    rows: list[dict[str, str]] = []
    for family, filename, pattern_class, semantics in INDUSTRY_INSPIRED_PATTERNS:
        source = LEGACY_ROOT / family / filename
        if not source.is_file():
            raise FileNotFoundError(f"industry-inspired source query not found: {source}")
        destination = destination_root / family / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        rows.append(
            {
                "query_id": source.stem,
                "path": f"{family}/{filename}",
                "stratum": "industry_inspired_synthetic",
                "family": family,
                "source": f"outerjoin_query_old/{family}/{filename}",
                "pattern_class": pattern_class,
                "semantics": semantics,
                "industry_status": "industry_inspired_not_industry_derived",
                "production_source_id": "none",
                "content_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )

    fields = list(rows[0])
    with (destination_root / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def generate_timeout_manifest(root: Path) -> int:
    timeout_paths = reference_timeouts()
    rows = [
        {
            "path": row["sql_path"],
            "family": row["family"],
            "query_id": row["query"],
            "disposition": "excluded_timeout",
            "reference_result": REFERENCE_RESULT.name,
            "reference_note": row["note"],
        }
        for row in load_reference_rows()
        if row["sql_path"] in timeout_paths
    ]
    fields = list(rows[0])
    with (root / "timeout_exclusions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def classify_legacy(root: Path) -> int:
    retained = {f"{family}/{filename}" for family, filename, _ in supplemental_stress()}
    industry_inspired = {
        f"{family}/{filename}"
        for family, filename, _, _ in INDUSTRY_INSPIRED_PATTERNS
    }
    timeouts = reference_timeouts()
    rows: list[dict[str, str]] = []
    sources = [
        (source, LEGACY_ROOT)
        for source in sorted(LEGACY_ROOT.glob("*/*.sql"))
    ] + [
        (source, TIMEOUT_ROOT)
        for source in sorted(TIMEOUT_ROOT.glob("*/*.sql"))
    ]
    for source, source_root in sources:
        relative = str(source.relative_to(source_root))
        family = source.parent.name
        if relative in timeouts:
            disposition = "excluded_timeout"
            provenance = "legacy_timeout"
            reason = f"excluded by {REFERENCE_RESULT.name}"
        elif relative in retained:
            disposition = "retain_supplemental"
            provenance = "synthetic_optimizer_stress"
            reason = "retained for optimizer characterization; selected after observed performance"
        elif relative in industry_inspired:
            disposition = "retain_industry_inspired"
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
                "content_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )

    fields = list(rows[0])
    with (root / "legacy_classification.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def validate_generated(root: Path) -> None:
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

    mixed_rows = [row for row in manifest_rows if len(set(row["join_vector"])) > 1]
    uniform_rows = [row for row in manifest_rows if len(set(row["join_vector"])) == 1]
    if len(mixed_rows) != 102 or len(uniform_rows) != 68:
        raise RuntimeError(
            f"unexpected mixed/control split: mixed={len(mixed_rows)}, "
            f"uniform={len(uniform_rows)}"
        )
    if any(not row["query_id"].rsplit("_", 1)[-1].startswith(("ldu", "rdu")) for row in uniform_rows):
        raise RuntimeError("only lduX/rduX variants may be uniform controls")

    uniform_kinds = Counter(row["join_vector"][0] for row in uniform_rows)
    if uniform_kinds != Counter({"L": 23, "R": 23, "F": 22}):
        raise RuntimeError(f"uniform controls are not join-kind balanced: {uniform_kinds}")
    uniform_shapes = Counter(row["tree_shape"] for row in uniform_rows)
    if uniform_shapes != Counter({"left_deep": 34, "right_deep": 34}):
        raise RuntimeError(f"uniform controls are not shape balanced: {uniform_shapes}")
    all_shapes = Counter(row["tree_shape"] for row in manifest_rows)
    if all_shapes != Counter({"left_deep": 80, "right_deep": 68, "bushy": 22}):
        raise RuntimeError(f"unexpected core shape distribution: {all_shapes}")

    for relative_path in sorted(actual_paths):
        sql = (root / "core" / relative_path).read_text(encoding="utf-8")
        upper = sql.upper()
        if "OUTER JOIN" not in upper:
            raise RuntimeError(f"{relative_path}: no outer join")
        if " ON 1=1" in upper:
            raise RuntimeError(f"{relative_path}: cross product")
        if any(token in upper for token in ("GROUP BY", "SELECT DISTINCT", " OVER (")):
            raise RuntimeError(f"{relative_path}: outside core applicability envelope")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--core-only", action="store_true")
    args = parser.parse_args()

    args.root.mkdir(parents=True, exist_ok=True)
    core_count = generate_core(args.root)
    supplemental_count = 0 if args.core_only else generate_supplemental(args.root)
    industry_count = 0 if args.core_only else generate_industry_inspired(args.root)
    timeout_count = generate_timeout_manifest(args.root)
    legacy_count = classify_legacy(args.root)
    validate_generated(args.root)
    print(
        f"generated {core_count} core, {industry_count} industry-inspired, and "
        f"{supplemental_count} supplemental queries; "
        f"excluded {timeout_count} timeouts and classified {legacy_count} legacy queries "
        f"under {args.root}"
    )


if __name__ == "__main__":
    main()
