"""Frozen exact-SQL removals applied after all benchmark transformations."""
from collections import Counter
import json

import balanced_benchmark as b
from workload_policy import validate_pins

POLICY = b.ROOT / "sources/retirements_20261009.json"
MARKER = "retirements.json"


def policy():
    spec = json.loads(POLICY.read_text())
    validate_pins(spec)
    return spec


def archived_rows(spec=None):
    spec = spec or policy()
    archive = b.ROOT / "revisions" / spec["archive_revision"] / "benchmark"
    rows = b.read_manifest(archive / "manifest.csv")
    pins = {r["query_id"]: r for r in spec["excluded"]}
    if len(rows) != len(pins) or {r["query_id"] for r in rows} != set(pins):
        raise ValueError("Retirement archive is incomplete")
    for row in rows:
        pin = pins[row["query_id"]]
        if any(row[k] != pin[k] for k in ("family", "path", "sql_fingerprint", "content_sha256")):
            raise ValueError("Retirement archive identity changed")
        if b.digest(archive / row["path"]) != row["content_sha256"]:
            raise ValueError("Retirement archive SQL changed")
    return rows, {r["path"]: archive / r["path"] for r in rows}


def marker(spec):
    return dict(revision=spec["revision"], policy_sha256=b.digest(POLICY),
                counts=spec["expected_counts_after"], removed_queries=len(spec["excluded"]))


def apply(records, output):
    spec = policy()
    archived, _ = archived_rows(spec)
    if dict(Counter(r["family"] for r in records)) != spec["expected_counts_before"]:
        raise ValueError("Retirement input counts changed")
    expected = {r["query_id"]: r for r in archived}
    targets = [r for r in records if r["query_id"] in expected]
    if len(targets) != len(expected):
        raise ValueError("Retirement target missing")
    # Validate every target before removing any staged SQL.
    for row in targets:
        old = expected[row["query_id"]]
        if any(row[k] != old[k] for k in ("family", "path", "content_sha256", "sql_fingerprint")):
            raise ValueError("Retirement metadata changed")
        if b.digest(output / row["path"]) != row["content_sha256"]:
            raise ValueError("Retirement SQL changed")
    removed = {r["path"] for r in targets}
    for path in removed:
        (output / path).unlink()
    for path in output.glob("*.txt"):
        lines = path.read_text().splitlines(keepends=True)
        path.write_text("".join(line for line in lines if line.strip() not in removed))
    retained = [r for r in records if r["query_id"] not in expected]
    if dict(Counter(r["family"] for r in retained)) != spec["expected_counts_after"]:
        raise ValueError("Retirement output counts changed")
    b.write_json(output / MARKER, marker(spec))
    return retained


def validate(benchmark, rows):
    """Restore historical metadata only for validation of earlier generator stages."""
    spec = policy()
    if json.loads((benchmark / MARKER).read_text()) != marker(spec):
        raise ValueError("Retirement policy changed; regenerate")
    if dict(Counter(r["family"] for r in rows)) != spec["expected_counts_after"]:
        raise ValueError("Retirement counts changed")
    retired, paths = archived_rows(spec)
    for key in ("query_id", "path", "sql_fingerprint"):
        if {r[key] for r in rows} & {r[key] for r in retired}:
            raise ValueError("Retired SQL is still active")
    for path in benchmark.glob("*.txt"):
        if set(path.read_text().splitlines()) & set(paths):
            raise ValueError("Retired SQL is still in a query list")
    return rows + retired, paths
