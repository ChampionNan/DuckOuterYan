"""Fail-closed verification of a shared PG-tree/native-DuckDB realization.

This compares typed join trees, not complete physical plans or predicates. It
applies only to queries over at least three distinct tables in the default
schema. The caller captures both plans for the same bare SQL and keeps the
source EXPLAIN/profile artifacts. A successful result permits measuring the
native DuckDB plan once and labeling that measurement as shared; it is not an
independent PG replay measurement.
"""

import hashlib
import re

from plans import semantic


_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*\Z")
_WHITESPACE = " \t\n\r\f\v"


def query_sha256(sql):
    """Hash the harness's simple bare SELECT, preserving internal SQL text.

    Normalize line endings, edge whitespace and one terminal semicolon, as
    replay's SQL hash does. Comments and embedded semicolons are deliberately
    outside this bounded helper's scope; callers should supply the executed
    SQL text, not an EXPLAIN wrapper or a setup script.
    """
    if not isinstance(sql, str):
        raise ValueError("query must be SQL text")
    canonical = sql.replace("\r\n", "\n").replace("\r", "\n").strip(_WHITESPACE)
    if canonical.endswith(";"):
        canonical = canonical[:-1].rstrip(_WHITESPACE)
    if (not re.match(r"SELECT\b", canonical, re.I) or
            any(token in canonical for token in (";", "--", "/*", "*/"))):
        raise ValueError("expected one bare SELECT without comments or embedded semicolons")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _relations(tree, label):
    relations = []

    def visit(node):
        if not isinstance(node, dict):
            raise ValueError(label + ": malformed plan node")
        if node.get("op") == "scan":
            relation = node.get("relation")
            if not isinstance(relation, str) or not _IDENTIFIER.fullmatch(relation):
                raise ValueError(label + ": expected a canonical unqualified table name")
            if node.get("schema", "main") not in {"main", "public"}:
                raise ValueError(label + ": only the mapped default schema is supported")
            occurrence = node.get("occurrence", 0)
            if type(occurrence) is not int or occurrence != 0:
                raise ValueError(label + ": repeated table occurrences are unsupported")
            if "left" in node or "right" in node or node.get("children"):
                raise ValueError(label + ": unexpected subtree beneath a scan")
            relations.append(relation)
        elif node.get("op") == "join":
            if node.get("join_type") not in {"inner", "left", "right", "full"}:
                raise ValueError(label + ": unsupported join type")
            if "left" not in node or "right" not in node or node.get("children"):
                raise ValueError(label + ": expected exactly two named join children")
            visit(node["left"])
            visit(node["right"])
        else:
            raise ValueError(label + ": unsupported plan node")

    visit(tree)
    if len(relations) != len(set(relations)):
        raise ValueError(label + ": duplicate base-table leaves are unsupported")
    return relations


def verify_shared_baseline(pg_tree, native_tree, expected_relations, *, sql,
                           pg_query_sha256, native_query_sha256,
                           profile_tree=None, profile_sql=None):
    """Return auditable identity evidence, or raise before any shared labeling.

    Trees use the representation returned by ``plans.pg_tree/duck_tree``.
    ``expected_relations`` is the independent query manifest, not plan-derived.
    Query hashes must come from each capture's executed bare SQL. Supplying a
    profile requires both its extracted tree and recorded ``query_name``.

    Equality allows physical child swaps (including LEFT/RIGHT inversion), but
    requires identical grouping, join types and preserved sides. No timings are
    accepted or generated. The caller must preserve normal native optimizer
    settings and validate query results separately.
    """
    if isinstance(expected_relations, str):
        raise ValueError("expected_relations must be a collection of table names")
    expected = list(expected_relations)
    if (len(expected) < 3 or any(not isinstance(r, str) or not _IDENTIFIER.fullmatch(r)
                                 for r in expected) or len(expected) != len(set(expected))):
        raise ValueError("manifest must contain at least three distinct canonical base tables")
    actual_hash = query_sha256(sql)
    for label, digest in (("PostgreSQL", pg_query_sha256), ("native DuckDB", native_query_sha256)):
        if digest != actual_hash:
            raise ValueError(label + ": captured query identity mismatch")
    if (profile_tree is None) != (profile_sql is None):
        raise ValueError("profile tree and original profile query must be supplied together")
    trees = [("PostgreSQL", pg_tree), ("native DuckDB", native_tree)]
    if profile_tree is not None:
        if query_sha256(profile_sql) != actual_hash:
            raise ValueError("native profile: captured query identity mismatch")
        trees.append(("native profile", profile_tree))
    signatures = {}
    for label, tree in trees:
        relations = _relations(tree, label)
        if len(relations) != len(expected):
            raise ValueError(label + ": base-table count does not match the query manifest")
        if set(relations) != set(expected):
            raise ValueError(label + ": base-table identities do not match the query manifest")
        signatures[label] = semantic(tree)
    if len(set(signatures.values())) != 1:
        raise ValueError("typed join-tree mismatch: grouping, join types or preserved sides differ")
    return {
        "status": "verified_shared_native_realization",
        "realization": "unmodified_native_duckdb",
        "display_label": "PG-Plan / DuckDB (shared native realization)",
        "independent_pg_replay_measurement": False,
        "measurement_policy": "measure_native_once_and_label_as_shared",
        "query_sha256": actual_hash,
        "relations": sorted(expected),
        "relation_count": len(expected),
        "semantic_signature": signatures["PostgreSQL"],
        "signatures": signatures,
        "native_profile_verified": profile_tree is not None,
        "comparison_scope": "typed join grouping, join types and preserved sides",
    }
