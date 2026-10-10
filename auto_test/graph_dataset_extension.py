"""Three user-pinned short Graph queries moved to Epinions before new timing."""
import json
import shutil
from collections import Counter

import balanced_benchmark as b
import prepare_graph_dataset_retest as retest

POLICY = b.ROOT / "sources/graph_dataset_extension_20261010.json"
CANDIDATES = b.ROOT / "graph_dataset_retest/epinions_extension"
ARCHIVE_REVISION = "replaced_graph_bitcoin_extension_20261010"
ARCHIVE = b.ROOT / "revisions" / ARCHIVE_REVISION / "benchmark"
MARKER = "graph_dataset_extension.json"
MANIFEST_SHA = "2e17cf3d28d3a8795fd8effd6c579b41fffead332e99244532e63eca4a6a5daf"
PIN_FIELDS = ("query_id", "path", "family", "content_sha256", "sql_fingerprint")


def candidates():
    if b.digest(CANDIDATES / "manifest.csv") != MANIFEST_SHA:
        raise ValueError("Graph extension manifest changed")
    rows = b.read_manifest(CANDIDATES / "manifest.csv")
    pins = {r["query_id"]: r for r in retest.load_policy(POLICY)["replacements"]}
    if len(rows) != 3 or {r["graph_dataset_source_query"] for r in rows} != set(pins):
        raise ValueError("Incomplete Graph extension")
    for row in rows:
        if (row["graph_dataset_source_sha256"] != pins[row["graph_dataset_source_query"]]["content_sha256"]
                or row["graph_dataset"] != "epinions"
                or b.digest(CANDIDATES / row["path"]) != row["content_sha256"]):
            raise ValueError("Graph extension SQL changed")
    return rows


def marker():
    return dict(revision="graph-dataset-extension-20261010", replaced_queries=3,
                candidate_manifest_sha256=MANIFEST_SHA, policy_sha256=b.digest(POLICY),
                dataset_counts={"bitcoin": 156, "epinions": 18})


def archived_rows():
    rows = b.read_manifest(ARCHIVE / "manifest.csv")
    pins = {r["query_id"]: r for r in retest.load_policy(POLICY)["replacements"]}
    if len(rows) != 3 or {r["query_id"] for r in rows} != set(pins):
        raise ValueError("Incomplete Graph extension archive")
    for row in rows:
        if (any(row[k] != pins[row["query_id"]][k] for k in PIN_FIELDS)
                or b.digest(ARCHIVE / row["path"]) != row["content_sha256"]):
            raise ValueError("Graph extension archive changed")
    return rows


def apply(records, output):
    replacements = {r["graph_dataset_source_query"]: r for r in candidates()}
    old = {r["query_id"]: r for r in archived_rows()}
    if not set(old).issubset(r["query_id"] for r in records):
        raise ValueError("Missing Graph extension sources")
    updated, paths = [], {}
    for row in records:
        if row["query_id"] not in replacements:
            updated.append(row)
            continue
        if (any(str(row[k]) != old[row["query_id"]][k] for k in PIN_FIELDS)
                or b.digest(output / row["path"]) != row["content_sha256"]):
            raise ValueError("Graph extension source changed")
        new = replacements[row["query_id"]]
        shutil.copyfile(CANDIDATES / new["path"], output / new["path"])
        (output / row["path"]).unlink()
        paths[row["path"]] = new["path"]
        updated.append(dict(new))
    for path in output.glob("*.txt"):
        path.write_text("".join(paths.get(line, line) + "\n" for line in path.read_text().splitlines()))
    b.write_json(output / MARKER, marker())
    return updated


def validate(benchmark, rows):
    if json.loads((benchmark / MARKER).read_text()) != marker():
        raise ValueError("Graph extension marker changed")
    expected = {r["query_id"]: r for r in candidates()}
    old = {r["query_id"]: r for r in archived_rows()}
    actual = [r for r in rows if r["query_id"] in expected]
    if len(actual) != 3 or set(old).intersection(r["query_id"] for r in rows):
        raise ValueError("Incomplete or duplicated Graph extension")
    for row in actual:
        if (any(str(row.get(k, "")) != str(v) for k, v in expected[row["query_id"]].items())
                or b.digest(benchmark / row["path"]) != row["content_sha256"]):
            raise ValueError("Graph extension metadata or SQL changed")
    if Counter(r.get("graph_dataset") for r in rows if r["family"] == "graph") != marker()["dataset_counts"]:
        raise ValueError("Graph extension dataset counts changed")
    for path in benchmark.glob("*.txt"):
        if set(path.read_text().splitlines()).intersection(r["path"] for r in old.values()):
            raise ValueError("Replaced Graph SQL remains in query list")
    return ([old[r["graph_dataset_source_query"]] if r["query_id"] in expected else r for r in rows],
            {r["path"]: ARCHIVE / r["path"] for r in old.values()})
