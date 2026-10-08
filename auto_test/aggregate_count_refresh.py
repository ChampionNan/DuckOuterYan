"""Exact, reversible COUNT(*) replacements of pinned aggregation queries.

The new queries retain their joins, filters and grouping, but have new identities
and require new measurements. No experiment results are read during generation.
"""
import hashlib
import json
from pathlib import Path
import re

import balanced_benchmark as b

POLICY = b.ROOT / "sources/aggregate_count_refresh_20261008.json"
MARKER = "aggregate_count_refresh.json"
QUERY_LIST = "aggregate_count_refresh.txt"
PIN_FIELDS = ("query_id", "path", "content_sha256", "sql_fingerprint", "family", "aggregate_variant")
IDENTIFIER = r"[A-Za-z_][A-Za-z_0-9]*"
COLUMN = IDENTIFIER + r"\." + IDENTIFIER
SELECT = re.compile(
    r"^SELECT\s+(?P<group>" + COLUMN + r")\s+AS\s+group_key\s*,\s*"
    r"(?P<expression>(?P<function>SUM|MIN|MAX)\s*\(\s*(?P<anchor>" + COLUMN + r")\s*\)"
    r"\s+AS\s+" + IDENTIFIER + r")(?=\s*\nFROM\b)", re.I | re.M)
COUNT_SELECT = re.compile(
    r"^SELECT\s+" + COLUMN + r"\s+AS\s+group_key\s*,\s*"
    r"(?P<expression>COUNT\(\*\) AS row_count)(?=\s*\nFROM\b)", re.I | re.M)


def policy():
    spec = json.loads(POLICY.read_text(encoding="utf-8"))
    replacements = spec["replacements"]
    if not replacements or len(replacements) != spec["expected_replacements"]:
        raise ValueError("Aggregate COUNT replacement count does not match its policy")
    for field in ("query_id", "path", "sql_fingerprint"):
        if len({r[field] for r in replacements}) != len(replacements):
            raise ValueError(f"Duplicate aggregate COUNT policy {field}")
    return spec


def _hash(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _header(revision, query):
    return f"-- aggregate_rewrite: {revision}; replaces: {query}; pending cpu9 measurement\n"


def _selection(content, variant):
    matches = list(SELECT.finditer(content))
    if len(matches) != 1 or variant != "grouped_" + matches[0]["function"].lower():
        raise ValueError("Expected one grouped MIN/MAX/SUM of a simple column")
    match = matches[0]
    grouping = r"\bGROUP\s+BY\s+" + re.escape(match["group"]) + r"\s*;\s*$"
    if not re.search(grouping, content, re.I):
        raise ValueError("Aggregate COUNT replacement must preserve its simple GROUP BY")
    return match


def transform(row, content, pinned, revision):
    """Replace only one pinned SELECT aggregate; preserve all remaining SQL bytes."""
    if any(str(row.get(k, "")) != str(pinned[k]) for k in PIN_FIELDS):
        raise ValueError(f"Aggregate replacement metadata changed: {pinned['query_id']}")
    if _hash(content) != pinned["content_sha256"] or b.sql_fingerprint(content, row["family"]) != pinned["sql_fingerprint"]:
        raise ValueError(f"Aggregate replacement source hash changed: {pinned['query_id']}")
    match = _selection(content, row["aggregate_variant"])
    suffix = "__" + row["aggregate_variant"]
    if not row["query_id"].endswith(suffix) or Path(row["path"]).stem != row["query_id"]:
        raise ValueError(f"Unexpected aggregate replacement identity: {row['query_id']}")
    query = row["query_id"][:-len(suffix)] + "__grouped_count"
    path = str(Path(row["path"]).with_name(query + ".sql"))
    rewritten = (content[:match.start("expression")] + "COUNT(*) AS row_count" +
                 content[match.end("expression"):])
    rewritten = _header(revision, row["query_id"]) + rewritten
    if b.expression_key(rewritten, row["family"]) != b.expression_key(content, row["family"]):
        raise ValueError("Aggregate replacement changed the join expression")
    result = dict(row, query_id=query, path=path, aggregate_variant="grouped_count", aggregate_anchor="",
                  aggregate_rewrite_revision=revision, replaces_query_id=row["query_id"],
                  replaces_content_sha256=row["content_sha256"],
                  qualification_status="PENDING_CPU9_MEASUREMENT",
                  sql_fingerprint=b.sql_fingerprint(rewritten, row["family"]), content_sha256=_hash(rewritten))
    return result, rewritten


def apply(records, output):
    """Validate the entire replacement set before changing staged generation files."""
    spec = policy()
    pins = {r["query_id"]: r for r in spec["replacements"]}
    selected = [r for r in records if r["query_id"] in pins]
    if len(selected) != len(pins) or {r["query_id"] for r in selected} != set(pins):
        raise ValueError("Aggregate replacement targets are missing or duplicated")
    replacements, marker_rows = {}, []
    for row in selected:
        content = (output / row["path"]).read_text(encoding="utf-8")
        new, sql = transform(row, content, pins[row["query_id"]], spec["revision"])
        replacements[row["query_id"]] = (new, sql)
        marker_rows.append(dict(query_id=new["query_id"], path=new["path"],
                                replaces_query_id=row["query_id"], content_sha256=new["content_sha256"],
                                previous_aggregate_expression=_selection(content, row["aggregate_variant"])["expression"]))
    updated = [replacements[r["query_id"]][0] if r["query_id"] in replacements else r for r in records]
    for field in ("query_id", "path", "sql_fingerprint"):
        if len({r[field] for r in updated}) != len(updated):
            raise ValueError(f"Duplicate aggregate COUNT replacement {field}")
    for old in selected:
        new, sql = replacements[old["query_id"]]
        target = output / new["path"]
        if target.exists():
            raise ValueError(f"Aggregate replacement target already exists: {target}")
    for old in selected:
        new, sql = replacements[old["query_id"]]
        (output / new["path"]).write_text(sql, encoding="utf-8")
        (output / old["path"]).unlink()  # only freshly generated staging SQL
    b.write_json(output / MARKER, dict(revision=spec["revision"], policy_sha256=b.digest(POLICY),
                 replacements=marker_rows, replaced_queries=len(selected), status="PENDING_CPU9_MEASUREMENT",
                 note="COUNT(*) changes aggregate semantics; prior runtime and correctness results do not apply."))
    (output / QUERY_LIST).write_text("".join(replacements[r["query_id"]][0]["path"] + "\n"
                                            for r in spec["replacements"]), encoding="utf-8")
    return updated


def archive_retired(destination, old_rows, root):
    """Keep exact old definitions recoverable before publishing the replacement set."""
    import tpcds_refresh
    spec = policy()
    tpcds_refresh.archive_retired(destination, old_rows, root, exclusions=spec["replacements"],
                                 revision=spec["archive_revision"])


def validate(benchmark, rows, retired_paths=None):
    """Reverse the projection edit and verify its original policy-pinned hash."""
    spec = policy()
    retired_paths = retired_paths or {}
    marker = json.loads((benchmark / MARKER).read_text(encoding="utf-8"))
    if marker.get("policy_sha256") != b.digest(POLICY) or marker.get("revision") != spec["revision"]:
        raise ValueError("Aggregate COUNT policy changed; regenerate")
    pins = {r["query_id"]: r for r in spec["replacements"]}
    actual = [r for r in rows if r.get("aggregate_rewrite_revision") == spec["revision"]]
    evidence = marker["replacements"]
    if (marker.get("replaced_queries") != len(pins) or len(actual) != len(pins) or
            len(evidence) != len(pins) or {r.get("replaces_query_id") for r in actual} != set(pins) or
            {r["replaces_query_id"] for r in evidence} != set(pins)):
        raise ValueError("Incomplete aggregate COUNT replacement set")
    if any(r["query_id"] in pins for r in rows):
        raise ValueError("An original aggregate replacement query is still active")
    evidence = {r["replaces_query_id"]: r for r in evidence}
    historical = {}
    for row in actual:
        pinned = pins[row["replaces_query_id"]]
        entry = evidence[pinned["query_id"]]
        content = retired_paths.get(row["path"], benchmark / row["path"]).read_text(encoding="utf-8")
        prefix = _header(spec["revision"], pinned["query_id"])
        if not content.startswith(prefix):
            raise ValueError("Aggregate COUNT identity header changed")
        old_content = content[len(prefix):]
        matches = list(COUNT_SELECT.finditer(old_content))
        if len(matches) != 1:
            raise ValueError("Aggregate COUNT SELECT list changed")
        match = matches[0]
        old_content = (old_content[:match.start("expression")] + entry["previous_aggregate_expression"] +
                       old_content[match.end("expression"):])
        old_row = dict(row, **pinned)
        for key in ("aggregate_rewrite_revision", "replaces_query_id", "replaces_content_sha256"):
            old_row.pop(key, None)
        old_row["aggregate_anchor"] = _selection(old_content, pinned["aggregate_variant"])["anchor"]
        expected, expected_sql = transform(old_row, old_content, pinned, spec["revision"])
        if expected_sql != content or any(str(row.get(k, "")) != str(v) for k, v in expected.items()):
            raise ValueError(f"Aggregate COUNT content or metadata changed: {row['query_id']}")
        if any(entry[k] != row[k] for k in ("query_id", "path", "content_sha256")):
            raise ValueError("Aggregate COUNT marker identity changed")
        historical[row["query_id"]] = old_row
    replacement_paths = {r["replaces_query_id"]: r["path"] for r in actual}
    expected_list = "".join(replacement_paths[pin["query_id"]] + "\n"
                            for pin in spec["replacements"]
                            if replacement_paths[pin["query_id"]] not in retired_paths)
    if (benchmark / QUERY_LIST).read_text(encoding="utf-8") != expected_list:
        raise ValueError("Aggregate COUNT query list changed")
    return [historical.get(r["query_id"], r) for r in rows]
