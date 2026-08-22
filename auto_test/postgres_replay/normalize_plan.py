#!/usr/bin/env python3
"""Normalize PostgreSQL EXPLAIN JSON into DuckYan's typed join-tree format.

This module intentionally uses only the Python standard library.  It is also
importable so extractor behavior can be covered by small, checked-in fixtures.
PostgreSQL expressions are diagnostic strings; DuckDB never binds them.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile


FORMAT = "duckyan.pg_join_tree.v1"
QUERY_CANONICALIZATION = "duckyan.sql_text.v1"
SUPPORTED_VERSION = 160002
DEFAULT_PLAN_SCHEMA = "public"
DEFAULT_PLAN_DATA = "tpch-sf0.01"

_SAMPLED_PLAN_DATA = re.compile(
    r"^(graph|tpcds|job)-duckdb-sample-([1-9][0-9]*)$"
)
_PLAN_SCHEMA = re.compile(r"^[a-z_][a-z0-9_]*$")

JOIN_NODES = {"Hash Join", "Merge Join", "Nested Loop"}
JOIN_TYPES = {"inner", "left", "right", "full"}
TRANSPARENT_NODES = {"Hash", "Sort", "Incremental Sort", "Materialize", "Memoize"}
# These operators can change rows, so they are transparent only at the root.
# DuckDB keeps its own already-bound aggregate; PGPlan imports only the join
# decision below it.
ROOT_CAP_NODES = {"Aggregate"}
SCAN_NODES = {
    "Seq Scan",
    "Index Scan",
    "Index Only Scan",
    "Bitmap Heap Scan",
    "Tid Scan",
    "Tid Range Scan",
}
BITMAP_ACCESS_NODES = {"Bitmap Index Scan", "BitmapAnd", "BitmapOr"}

PREDICATE_KEYS = (
    "Hash Cond",
    "Merge Cond",
    "Join Filter",
    "Filter",
    "Index Cond",
    "Recheck Cond",
    "TID Cond",
)

ASCII_WHITESPACE = " \t\r\n\f\v"
_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")

_TABLE_ALIAS_STOP_WORDS = {
    "inner",
    "left",
    "right",
    "full",
    "outer",
    "cross",
    "join",
    "on",
    "using",
    "where",
    "group",
    "having",
    "order",
    "limit",
    "offset",
    "fetch",
    "union",
    "intersect",
    "except",
}


class PlanError(ValueError):
    """Raised when a plan cannot be represented safely by PGPlan v1."""


def canonicalize_query(query_bytes):
    """Validate one SELECT and return the bytes hashed by both tools.

    Canonicalization removes leading whitespace/comments (DuckDB exposes the
    active statement beginning at its first SQL token), trims one optional
    final semicolon, and otherwise remains byte-exact.  A small PostgreSQL-aware
    scanner prevents a second statement from being smuggled into psql capture.
    """
    try:
        text = query_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlanError("query must be valid UTF-8") from exc
    if "\x00" in text:
        raise PlanError("query contains a NUL byte")

    # Keep hashes stable when the same query file crosses Unix/Windows hosts.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.rstrip(ASCII_WHITESPACE)
    text = text[_first_sql_token_offset(text) :]
    if not text:
        raise PlanError("query is empty")

    semicolons = _top_level_semicolons(text)
    if len(semicolons) > 1:
        raise PlanError("query file must contain exactly one SQL statement")
    if semicolons:
        semicolon = semicolons[0]
        if text[semicolon + 1 :].strip(ASCII_WHITESPACE):
            raise PlanError("only ASCII whitespace may follow the final semicolon")
        text = text[:semicolon].rstrip(ASCII_WHITESPACE)

    keyword = _first_sql_keyword(text)
    if keyword != "select":
        raise PlanError("PGPlan v1 capture requires one SELECT statement")
    return text.encode("utf-8")


def _top_level_semicolons(text):
    semicolons = []
    index = 0
    length = len(text)
    state = "normal"
    block_depth = 0
    dollar_delimiter = None

    while index < length:
        char = text[index]
        next_char = text[index + 1] if index + 1 < length else ""

        if state == "normal":
            if char == "'":
                state = "single"
            elif char == '"':
                state = "double"
            elif char == "-" and next_char == "-":
                state = "line_comment"
                index += 1
            elif char == "/" and next_char == "*":
                state = "block_comment"
                block_depth = 1
                index += 1
            elif char == "$":
                match = _DOLLAR_TAG.match(text, index)
                if match:
                    dollar_delimiter = match.group(0)
                    state = "dollar"
                    index = match.end() - 1
            elif char == ";":
                semicolons.append(index)
        elif state == "single":
            if char == "'" and next_char == "'":
                index += 1
            elif char == "'":
                state = "normal"
        elif state == "double":
            if char == '"' and next_char == '"':
                index += 1
            elif char == '"':
                state = "normal"
        elif state == "line_comment":
            if char in "\r\n":
                state = "normal"
        elif state == "block_comment":
            if char == "/" and next_char == "*":
                block_depth += 1
                index += 1
            elif char == "*" and next_char == "/":
                block_depth -= 1
                index += 1
                if block_depth == 0:
                    state = "normal"
        elif state == "dollar":
            if text.startswith(dollar_delimiter, index):
                index += len(dollar_delimiter) - 1
                state = "normal"
                dollar_delimiter = None
        index += 1

    if state in ("single", "double", "block_comment", "dollar"):
        raise PlanError("query contains an unterminated quoted string or comment")
    return semicolons


def _first_sql_token_offset(text):
    """Return the first token after leading whitespace and SQL comments."""
    index = 0
    length = len(text)
    while index < length:
        if text[index] in ASCII_WHITESPACE:
            index += 1
            continue
        if text.startswith("--", index):
            newline = text.find("\n", index + 2)
            if newline < 0:
                return length
            index = newline + 1
            continue
        if text.startswith("/*", index):
            depth = 1
            index += 2
            while index < length and depth:
                if text.startswith("/*", index):
                    depth += 1
                    index += 2
                elif text.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise PlanError("query contains an unterminated block comment")
            continue
        return index
    return length


def _first_sql_keyword(text):
    index = _first_sql_token_offset(text)
    match = re.match(r"[A-Za-z_][A-Za-z0-9_$]*", text[index:])
    return match.group(0).lower() if match else ""


def validate_plan_provenance(plan_schema, plan_data):
    if not isinstance(plan_schema, str) or not _PLAN_SCHEMA.fullmatch(plan_schema):
        raise PlanError(
            "plan schema must be a lowercase unquoted PostgreSQL identifier"
        )
    if plan_data == DEFAULT_PLAN_DATA:
        if plan_schema != DEFAULT_PLAN_SCHEMA:
            raise PlanError("tpch-sf0.01 must use the prepared public schema")
        return
    sampled = _SAMPLED_PLAN_DATA.fullmatch(plan_data or "")
    if not sampled:
        raise PlanError(
            "plan data must be tpch-sf0.01 or "
            "<graph|tpcds|job>-duckdb-sample-<positive rows>"
        )
    family = sampled.group(1)
    expected_schema = "pgplan_{}".format(family)
    if plan_schema != expected_schema:
        raise PlanError(
            "{} must use the prepared {} schema".format(plan_data, expected_schema)
        )


def render_explain_sql(query_bytes, plan_schema=DEFAULT_PLAN_SCHEMA):
    validate_plan_provenance(
        plan_schema,
        DEFAULT_PLAN_DATA if plan_schema == DEFAULT_PLAN_SCHEMA else
        "{}-duckdb-sample-1".format(plan_schema.removeprefix("pgplan_")),
    )
    query = canonicalize_query(query_bytes).decode("utf-8")
    setup = ""
    if plan_schema != DEFAULT_PLAN_SCHEMA:
        setup = "SET LOCAL search_path = {}, pg_catalog;\n".format(plan_schema)
    return (
        "BEGIN READ ONLY;\n"
        "SET LOCAL max_parallel_workers_per_gather = 0;\n"
        + setup
        + "EXPLAIN (FORMAT JSON, VERBOSE, COSTS TRUE, SETTINGS TRUE)\n"
        + query
        # A newline keeps the terminator out of a trailing -- comment.
        + "\n;\nROLLBACK;\n"
    )


def _identifier_tokens(text):
    """Return identifier/punctuation tokens while ignoring SQL literals/comments.

    This is deliberately a small scanner, not a SQL parser.  The supported
    corpus has base-table JOIN trees without subqueries or table functions;
    anything that cannot be mapped unambiguously fails closed later.
    """
    tokens = []
    index = 0
    length = len(text)
    state = "normal"
    block_depth = 0
    dollar_delimiter = None
    while index < length:
        char = text[index]
        next_char = text[index + 1] if index + 1 < length else ""
        if state == "normal":
            if char in ASCII_WHITESPACE:
                pass
            elif char == "'":
                state = "single"
            elif char == '"':
                cursor = index + 1
                value = []
                while cursor < length:
                    if text[cursor] == '"':
                        if cursor + 1 < length and text[cursor + 1] == '"':
                            value.append('"')
                            cursor += 2
                            continue
                        break
                    value.append(text[cursor])
                    cursor += 1
                if cursor >= length:
                    raise PlanError("query contains an unterminated quoted identifier")
                tokens.append(("identifier", "".join(value)))
                index = cursor
            elif char == "-" and next_char == "-":
                state = "line_comment"
                index += 1
            elif char == "/" and next_char == "*":
                state = "block_comment"
                block_depth = 1
                index += 1
            elif char == "$":
                match = _DOLLAR_TAG.match(text, index)
                if match:
                    dollar_delimiter = match.group(0)
                    state = "dollar"
                    index = match.end() - 1
                else:
                    tokens.append(("punctuation", char))
            elif char.isalpha() or char == "_":
                match = re.match(r"[A-Za-z_][A-Za-z0-9_$]*", text[index:])
                value = match.group(0)
                tokens.append(("identifier", value.lower()))
                index += len(value) - 1
            elif char in "().,;":
                tokens.append(("punctuation", char))
        elif state == "single":
            if char == "'" and next_char == "'":
                index += 1
            elif char == "'":
                state = "normal"
        elif state == "line_comment":
            if char in "\r\n":
                state = "normal"
        elif state == "block_comment":
            if char == "/" and next_char == "*":
                block_depth += 1
                index += 1
            elif char == "*" and next_char == "/":
                block_depth -= 1
                index += 1
                if block_depth == 0:
                    state = "normal"
        elif state == "dollar":
            if text.startswith(dollar_delimiter, index):
                index += len(dollar_delimiter) - 1
                state = "normal"
                dollar_delimiter = None
        index += 1
    if state in ("single", "block_comment", "dollar"):
        raise PlanError("query contains an unterminated quoted string or comment")
    return tokens


def _query_alias_occurrences(canonical_query):
    text = canonical_query.decode("utf-8")
    tokens = _identifier_tokens(text)
    by_alias = {}
    relation_counts = {}
    index = 0
    while index < len(tokens):
        kind, value = tokens[index]
        if kind != "identifier" or value not in ("from", "join"):
            index += 1
            continue
        cursor = index + 1
        while cursor < len(tokens) and tokens[cursor] == ("punctuation", "("):
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor][0] != "identifier":
            raise PlanError("unsupported FROM/JOIN source; expected a base table")
        first = tokens[cursor][1]
        cursor += 1
        relation = first
        if cursor + 1 < len(tokens) and tokens[cursor] == ("punctuation", "."):
            if tokens[cursor + 1][0] != "identifier":
                raise PlanError("malformed schema-qualified table reference")
            relation = tokens[cursor + 1][1]
            cursor += 2
        if relation in ("select", "values"):
            raise PlanError("subqueries and table-valued sources are unsupported")
        alias = relation
        if cursor < len(tokens) and tokens[cursor] == ("identifier", "as"):
            cursor += 1
            if cursor >= len(tokens) or tokens[cursor][0] != "identifier":
                raise PlanError("AS must be followed by a table alias")
            alias = tokens[cursor][1]
        elif cursor < len(tokens) and tokens[cursor][0] == "identifier":
            candidate = tokens[cursor][1]
            if candidate not in _TABLE_ALIAS_STOP_WORDS:
                alias = candidate
        alias_key = alias.casefold()
        if alias_key in by_alias:
            raise PlanError("duplicate table alias in query: {}".format(alias))
        relation_key = relation.casefold()
        occurrence = relation_counts.get(relation_key, 0)
        relation_counts[relation_key] = occurrence + 1
        by_alias[alias_key] = (relation_key, occurrence)
        index = cursor
    return by_alias


def _require_object(value, location):
    if not isinstance(value, dict):
        raise PlanError("{} must be a JSON object".format(location))
    return value


def _require_string(obj, key, location):
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise PlanError("{}.{} must be a non-empty string".format(location, key))
    return value


def _diagnostics(node):
    result = {"postgres_node_type": _require_string(node, "Node Type", "plan node")}
    for source, target in (
        ("Startup Cost", "startup_cost"),
        ("Total Cost", "total_cost"),
        ("Plan Rows", "plan_rows"),
        ("Plan Width", "plan_width"),
    ):
        if source in node:
            value = node[source]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise PlanError("plan node.{} must be numeric".format(source))
            result[target] = value

    predicates = {}
    for key in PREDICATE_KEYS:
        if key in node:
            value = node[key]
            if not isinstance(value, str):
                raise PlanError("plan node.{} must be a string".format(key))
            predicates[key.lower().replace(" ", "_")] = value
    if predicates:
        result["predicates"] = predicates

    output = node.get("Output")
    if output is not None:
        if not isinstance(output, list) or not all(isinstance(item, str) for item in output):
            raise PlanError("plan node.Output must be an array of strings")
        result["output"] = output
    return result


def _append_wrapper_diagnostic(normalized, diagnostic):
    details = normalized.setdefault("diagnostics", {})
    wrappers = details.setdefault("wrappers", [])
    wrappers.insert(0, diagnostic)


def _bitmap_access_diagnostics(node):
    node_type = _require_string(node, "Node Type", "bitmap access node")
    if node_type not in BITMAP_ACCESS_NODES:
        raise PlanError("unsupported child below Bitmap Heap Scan: {}".format(node_type))
    result = [_diagnostics(node)]
    plans = node.get("Plans", [])
    if not isinstance(plans, list):
        raise PlanError("bitmap access node.Plans must be an array")
    for child in plans:
        result.extend(_bitmap_access_diagnostics(_require_object(child, "bitmap child")))
    return result


def _normalize_node(node, plan_schema):
    node = _require_object(node, "plan node")
    node_type = _require_string(node, "Node Type", "plan node")

    if node_type in TRANSPARENT_NODES:
        plans = node.get("Plans")
        if not isinstance(plans, list) or len(plans) != 1:
            raise PlanError("transparent {} must have exactly one child".format(node_type))
        normalized = _normalize_node(plans[0], plan_schema)
        _append_wrapper_diagnostic(normalized, _diagnostics(node))
        return normalized

    if node_type in JOIN_NODES:
        join_type = _require_string(node, "Join Type", "{} node".format(node_type)).lower()
        if join_type not in JOIN_TYPES:
            raise PlanError("unsupported PostgreSQL join type: {}".format(join_type))
        plans = node.get("Plans")
        if not isinstance(plans, list) or len(plans) != 2:
            raise PlanError("{} must have exactly two children".format(node_type))

        by_relationship = {}
        for child in plans:
            child = _require_object(child, "{} child".format(node_type))
            relationship = _require_string(
                child, "Parent Relationship", "{} child".format(node_type)
            ).lower()
            if relationship not in ("outer", "inner"):
                raise PlanError(
                    "{} child has unsupported Parent Relationship {}".format(
                        node_type, relationship
                    )
                )
            if relationship in by_relationship:
                raise PlanError("{} has duplicate {} child".format(node_type, relationship))
            by_relationship[relationship] = child
        if set(by_relationship) != {"outer", "inner"}:
            raise PlanError("{} must have one Outer and one Inner child".format(node_type))

        return {
            "op": "join",
            "join_type": join_type,
            "left": _normalize_node(by_relationship["outer"], plan_schema),
            "right": _normalize_node(by_relationship["inner"], plan_schema),
            "diagnostics": _diagnostics(node),
        }

    if node_type in SCAN_NODES:
        schema = _require_string(node, "Schema", "{} node".format(node_type))
        relation = _require_string(node, "Relation Name", "{} node".format(node_type))
        alias = _require_string(node, "Alias", "{} node".format(node_type))
        if schema != plan_schema:
            prepared = (
                "prepared public schema"
                if plan_schema == DEFAULT_PLAN_SCHEMA
                else "prepared schema {}".format(plan_schema)
            )
            raise PlanError(
                "plan-selection scans must resolve to {}; got {}.{}".format(
                    prepared, schema, relation
                )
            )
        diagnostics = _diagnostics(node)
        diagnostics["source_schema"] = schema
        plans = node.get("Plans", [])
        if not isinstance(plans, list):
            raise PlanError("{} node.Plans must be an array".format(node_type))
        if plans:
            if node_type != "Bitmap Heap Scan":
                raise PlanError("{} scan unexpectedly has child plans".format(node_type))
            access_paths = []
            for child in plans:
                access_paths.extend(_bitmap_access_diagnostics(_require_object(child, "bitmap child")))
            diagnostics["access_paths"] = access_paths
        return {
            "op": "scan",
            # Every execution database stores its family in DuckDB's main
            # schema.  The source PG schema is provenance, not target identity.
            "schema": "public",
            "relation": relation,
            "alias": alias,
            "diagnostics": diagnostics,
        }

    raise PlanError("unsupported PostgreSQL plan node: {}".format(node_type))


def _normalize_root(node, plan_schema):
    node = _require_object(node, "plan node")
    node_type = _require_string(node, "Node Type", "plan node")
    if node_type in ROOT_CAP_NODES:
        plans = node.get("Plans")
        if not isinstance(plans, list) or len(plans) != 1:
            raise PlanError("root {} must have exactly one child".format(node_type))
        normalized = _normalize_root(plans[0], plan_schema)
        _append_wrapper_diagnostic(normalized, _diagnostics(node))
        return normalized
    return _normalize_node(node, plan_schema)


def _assign_occurrences(tree, alias_occurrences):
    relation_counts = {}

    def count(node):
        if node["op"] == "join":
            count(node["left"])
            count(node["right"])
            return
        relation_key = node["relation"].casefold()
        relation_counts[relation_key] = relation_counts.get(relation_key, 0) + 1

    def visit(node):
        if node["op"] == "join":
            visit(node["left"])
            visit(node["right"])
            return
        alias_key = node["alias"].casefold()
        mapping = alias_occurrences.get(alias_key)
        if mapping is None:
            relation_key = node["relation"].casefold()
            if not alias_occurrences and relation_counts.get(relation_key) == 1:
                node["occurrence"] = 0
                return
            if relation_counts.get(relation_key, 0) > 1:
                raise PlanError(
                    "self-joins require distinct aliases recoverable from the captured query"
                )
            raise PlanError(
                "PostgreSQL plan alias {} is absent from the captured query".format(
                    node["alias"]
                )
            )
        expected_relation, occurrence = mapping
        if node["relation"].casefold() != expected_relation:
            raise PlanError(
                "query alias {} names {}, but PostgreSQL planned {}".format(
                    node["alias"], expected_relation, node["relation"]
                )
            )
        node["occurrence"] = occurrence

    count(tree)
    visit(tree)


def _validate_unique_leaves(tree):
    relations = set()
    aliases = set()
    leaf_count = 0
    join_count = 0

    def visit(node):
        nonlocal leaf_count, join_count
        if node["op"] == "scan":
            identity = (node["schema"], node["relation"], node["occurrence"])
            if node["schema"] != "public":
                raise PlanError(
                    "normalized target scans must use the public/default schema; "
                    "got {}.{}".format(node["schema"], node["relation"])
                )
            if identity in relations:
                raise PlanError(
                    "duplicate table occurrence in normalized plan: {}.{}#{}".format(
                        *identity
                    )
                )
            if node["alias"] in aliases:
                raise PlanError("duplicate scan alias: {}".format(node["alias"]))
            relations.add(identity)
            aliases.add(node["alias"])
            leaf_count += 1
            return
        join_count += 1
        visit(node["left"])
        visit(node["right"])

    visit(tree)
    if leaf_count < 1 or join_count != leaf_count - 1:
        raise PlanError("PGPlan v1 requires one scan or a connected binary join tree")


def normalize_explain(
    explain_value,
    query_bytes,
    version_num,
    plan_schema=DEFAULT_PLAN_SCHEMA,
    plan_data=DEFAULT_PLAN_DATA,
):
    validate_plan_provenance(plan_schema, plan_data)
    if version_num != SUPPORTED_VERSION:
        raise PlanError(
            "PostgreSQL server_version_num must be {}, got {}".format(
                SUPPORTED_VERSION, version_num
            )
        )
    if not isinstance(explain_value, list) or len(explain_value) != 1:
        raise PlanError("EXPLAIN JSON must be a one-element array")
    statement = _require_object(explain_value[0], "EXPLAIN statement")
    if "Plan" not in statement:
        raise PlanError("EXPLAIN statement is missing Plan")

    settings = statement.get("Settings")
    if not isinstance(settings, dict):
        raise PlanError("EXPLAIN SETTINGS output is missing or not an object")
    expected_settings = {"max_parallel_workers_per_gather": "0"}
    if plan_schema != DEFAULT_PLAN_SCHEMA:
        expected_settings["search_path"] = "{}, pg_catalog".format(plan_schema)
    if settings != expected_settings:
        raise PlanError(
            "planner settings must be PostgreSQL defaults except the deterministic "
            "PGPlan settings {!r}; EXPLAIN reported {!r}".format(
                expected_settings, settings
            )
        )

    canonical_query = canonicalize_query(query_bytes)
    tree = _normalize_root(statement["Plan"], plan_schema)
    _assign_occurrences(tree, _query_alias_occurrences(canonical_query))
    _validate_unique_leaves(tree)
    return {
        "format": FORMAT,
        "query_sha256": hashlib.sha256(canonical_query).hexdigest(),
        "query_sha256_canonicalization": QUERY_CANONICALIZATION,
        "postgres": {
            "version_num": version_num,
            "settings": settings,
            "plan_schema": plan_schema,
            "plan_data": plan_data,
        },
        "tree": tree,
    }


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError("cannot read EXPLAIN JSON {}: {}".format(path, exc)) from exc


def _read_bytes(path):
    try:
        with open(path, "rb") as source:
            return source.read()
    except OSError as exc:
        raise PlanError("cannot read query {}: {}".format(path, exc)) from exc


def _write_json_atomic(path, value):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, prefix=".pg-plan-", delete=False
        ) as target:
            temporary = target.name
            json.dump(value, target, indent=2, ensure_ascii=False)
            target.write("\n")
        os.replace(temporary, path)
    except OSError as exc:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        raise PlanError("cannot write artifact {}: {}".format(path, exc)) from exc


def _parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--emit-explain-sql", action="store_true")
    mode.add_argument("--emit-canonical-query", action="store_true")
    mode.add_argument("--normalize", action="store_true")
    parser.add_argument("--query", required=True)
    parser.add_argument("--pg-schema", default=DEFAULT_PLAN_SCHEMA)
    parser.add_argument("--plan-data", default=DEFAULT_PLAN_DATA)
    parser.add_argument("--explain-json")
    parser.add_argument("--version-num", type=int)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    if args.normalize and not (args.explain_json and args.version_num is not None and args.out):
        parser.error("--normalize requires --explain-json, --version-num, and --out")
    return args


def main(argv=None):
    try:
        args = _parse_args(argv)
        query_bytes = _read_bytes(args.query)
        if args.emit_canonical_query:
            sys.stdout.buffer.write(canonicalize_query(query_bytes))
            return 0
        if args.emit_explain_sql:
            validate_plan_provenance(args.pg_schema, args.plan_data)
            sys.stdout.write(render_explain_sql(query_bytes, args.pg_schema))
            return 0
        artifact = normalize_explain(
            _load_json(args.explain_json),
            query_bytes,
            args.version_num,
            args.pg_schema,
            args.plan_data,
        )
        _write_json_atomic(args.out, artifact)
        return 0
    except PlanError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
