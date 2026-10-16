"""One pinned JOB predicate update; no result access during SQL generation."""
import hashlib
import json

import balanced_benchmark as b

POLICY = b.ROOT / "sources/job_selectivity_update_20261014.json"
MARKER = "job_selectivity_update.json"


def policy():
    return json.loads(POLICY.read_text())


def definition():
    spec = policy()
    old = spec["original"]
    source = b.ROOT / spec["original_archive"]
    if b.digest(source) != old["content_sha256"]:
        raise ValueError("Archived JOB source changed")
    sql = source.read_text()
    if sql.count(old["selectivity_predicate"]) != 1:
        raise ValueError("Expected exactly one JOB predicate")
    sql = sql.replace(old["selectivity_predicate"], spec["predicate"], 1)
    if hashlib.sha256(sql.encode()).hexdigest() != spec["content_sha256"]:
        raise ValueError("JOB candidate does not match measured SQL")
    calibration = spec["calibration"]
    fraction = calibration["qualified_rows"] / calibration["rows"]
    if not .05 <= fraction < .4:
        raise ValueError("JOB candidate must remain in the medium band")
    updates = dict(
        selectivity_predicate=spec["predicate"], target_fraction=str(fraction),
        calibration_rows=str(calibration["rows"]),
        calibration_qualified_rows=str(calibration["qualified_rows"]),
        calibration_fraction=str(fraction), calibration_in_range="true",
        filter_design_revision=spec["revision"],
        parameter_policy=spec["selection_disclosure"],
        content_sha256=spec["content_sha256"], sql_fingerprint=b.sql_fingerprint(sql, "job"))
    return updates, sql


def marker():
    spec = policy()
    return dict(revision=spec["revision"], query_id=spec["original"]["query_id"],
                policy_sha256=b.digest(POLICY), content_sha256=spec["content_sha256"])


def apply(rows, output):
    old = policy()["original"]
    matched = [r for r in rows if r["query_id"] == old["query_id"]]
    if len(matched) != 1:
        raise ValueError("Expected one JOB replacement source")
    row = matched[0]
    if any(str(row.get(k, "")) != v for k, v in old.items()):
        raise ValueError("JOB source metadata changed")
    if b.digest(output / row["path"]) != old["content_sha256"]:
        raise ValueError("JOB source SQL changed")
    updates, sql = definition()
    updated = [dict(r, **updates) if r is row else r for r in rows]
    if len({r["sql_fingerprint"] for r in updated}) != len(rows):
        raise ValueError("JOB replacement duplicates an existing query")
    (output / row["path"]).write_text(sql)
    b.write_json(output / MARKER, marker())
    return updated


def validate(corpus, rows):
    """Restore the original row/path for validators of earlier generator stages."""
    spec = policy()
    old = spec["original"]
    matched = [r for r in rows if r["query_id"] == old["query_id"]]
    if not (corpus / MARKER).exists():
        if any(r.get("content_sha256") == spec["content_sha256"] for r in matched):
            raise ValueError("JOB update marker missing")
        return rows, {}
    if json.loads((corpus / MARKER).read_text()) != marker() or len(matched) != 1:
        raise ValueError("JOB update marker or membership changed")
    updates, _ = definition()
    expected = dict(old, **updates)
    if any(str(matched[0].get(k, "")) != v for k, v in expected.items()):
        raise ValueError("JOB update metadata changed")
    if b.digest(corpus / old["path"]) != spec["content_sha256"]:
        raise ValueError("JOB update SQL changed")
    restored = [dict(old) if r["query_id"] == old["query_id"] else r for r in rows]
    return restored, {old["path"]: b.ROOT / spec["original_archive"]}
