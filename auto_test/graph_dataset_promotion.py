"""Frozen adoption of all 16 Epinions retest candidates, regardless of outcome.

Generation reads pinned SQL/metadata, never timing logs. Bitcoin source queries
remain recoverable in the revision archive. Dataset is part of query identity.
"""
import json
import shutil
from collections import Counter
from pathlib import Path

import balanced_benchmark as b
import prepare_graph_dataset_retest as retest
from benchmark_corpus import graph_query_dataset as query_dataset

MARKER = "graph_dataset_promotion.json"
ARCHIVE = b.ROOT / "revisions/replaced_graph_bitcoin_20261010/benchmark"
CANDIDATES = b.ROOT / "graph_dataset_retest/epinions"
MANIFEST_SHA = "0d41aea482115c47bd535556ea78a7e3a16a0e20c51fa998149475880fbd54c2"
PIN_FIELDS = ("query_id", "path", "content_sha256", "sql_fingerprint", "family")


def candidates():
    if b.digest(CANDIDATES / "manifest.csv") != MANIFEST_SHA:
        raise ValueError("Epinions candidate manifest changed")
    rows = b.read_manifest(CANDIDATES / "manifest.csv")
    pins = {r["query_id"]: r for r in retest.load_policy()["replacements"]}
    if len(rows) != 16 or {r["graph_dataset_source_query"] for r in rows} != set(pins):
        raise ValueError("Incomplete Epinions promotion cohort")
    for row in rows:
        old = pins[row["graph_dataset_source_query"]]
        if row["graph_dataset"] != "epinions" or row["graph_dataset_source_sha256"] != old["content_sha256"]:
            raise ValueError("Epinions source identity changed")
        path = Path(row["path"])
        if path.parts != ("graph", row["query_id"] + ".sql"):
            raise ValueError("Unsafe Epinions path")
        if b.digest(CANDIDATES / path) != row["content_sha256"]:
            raise ValueError("Epinions SQL changed")
    return rows


def marker():
    return dict(revision="graph-dataset-promotion-20261010", replaced_queries=16,
                dataset_counts={"bitcoin": 159, "epinions": 16},
                candidate_manifest_sha256=MANIFEST_SHA,
                policy="All 16 frozen short-query candidates adopted, including timeout and fallback outcomes",
                result_csv="experiment_onoff_graph_epinions_20261010_005733_t32.csv",
                result_csv_sha256="5b054ef96e1dc6a4cbe4329f5919d6abebd98d31563eef4d415b766e1b654e05")


def archive_sources(corpus):
    pins = {r["query_id"]: r for r in retest.load_policy()["replacements"]}
    rows = [r for r in b.read_manifest(corpus / "manifest.csv") if r["query_id"] in pins]
    if not rows and (ARCHIVE / "manifest.csv").exists():
        return archived_rows()
    if len(rows) != len(pins):
        raise ValueError("Missing Bitcoin promotion sources")
    for row in rows:
        if any(row[k] != pins[row["query_id"]][k] for k in PIN_FIELDS):
            raise ValueError("Bitcoin metadata changed before archive")
        if b.digest(corpus / row["path"]) != row["content_sha256"]:
            raise ValueError("Bitcoin SQL changed before archive")
        target = ARCHIVE / row["path"]
        if target.exists() and b.digest(target) != row["content_sha256"]:
            raise ValueError("Refusing to overwrite changed archived SQL")
    if (ARCHIVE / "manifest.csv").exists():
        if b.read_manifest(ARCHIVE / "manifest.csv") != rows:
            raise ValueError("Refusing to overwrite changed archive manifest")
    else:
        for row in rows:
            target = ARCHIVE / row["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(corpus / row["path"], target)
        b.write_csv(ARCHIVE / "manifest.csv", rows)
    return archived_rows()


def archived_rows():
    rows = b.read_manifest(ARCHIVE / "manifest.csv")
    pins = {r["query_id"]: r for r in retest.load_policy()["replacements"]}
    if len(rows) != len(pins) or {r["query_id"] for r in rows} != set(pins):
        raise ValueError("Incomplete Bitcoin archive")
    for row in rows:
        if any(row[k] != pins[row["query_id"]][k] for k in PIN_FIELDS):
            raise ValueError("Bitcoin archive metadata changed")
        if b.digest(ARCHIVE / row["path"]) != row["content_sha256"]:
            raise ValueError("Bitcoin archive SQL changed")
    return rows


def apply(records, output):
    targets = {r["graph_dataset_source_query"]: r for r in candidates()}
    source_rows = {r["query_id"]: r for r in records if r["query_id"] in targets}
    if len(source_rows) != 16:
        raise ValueError("Missing Graph promotion source in generation")
    archived = {r["query_id"]: r for r in archived_rows()}
    for query, row in source_rows.items():
        if any(str(row[k]) != archived[query][k] for k in PIN_FIELDS):
            raise ValueError("Generated Bitcoin source changed")
        if b.digest(output / row["path"]) != row["content_sha256"]:
            raise ValueError("Generated Bitcoin SQL changed")
        if (output / targets[query]["path"]).exists():
            raise ValueError("Duplicate promoted SQL target")
    updated = []
    path_map = {}
    for row in records:
        if row["query_id"] in targets:
            new = dict(targets[row["query_id"]])
            shutil.copyfile(CANDIDATES / new["path"], output / new["path"])
            (output / row["path"]).unlink()
            path_map[row["path"]] = new["path"]
        else:
            new = dict(row)
            if row["family"] == "graph":
                new["graph_dataset"] = "bitcoin"
        updated.append(new)
    for path in output.glob("*.txt"):
        lines = path.read_text().splitlines()
        path.write_text("".join(path_map.get(line, line) + "\n" for line in lines))
    b.write_json(output / MARKER, marker())
    return updated


def validate(benchmark, rows):
    """Return pre-promotion rows/paths to validate earlier generator stages."""
    if json.loads((benchmark / MARKER).read_text()) != marker():
        raise ValueError("Graph promotion marker changed")
    expected = {r["query_id"]: r for r in candidates()}
    old = {r["query_id"]: r for r in archived_rows()}
    if set(old).intersection(r["query_id"] for r in rows):
        raise ValueError("Replaced Bitcoin SQL is still active")
    actual = [r for r in rows if r["query_id"] in expected]
    if len(actual) != 16:
        raise ValueError("Missing promoted Epinions queries")
    for row in actual:
        if any(str(row.get(k, "")) != str(v) for k, v in expected[row["query_id"]].items()):
            raise ValueError("Promoted Epinions metadata changed")
        if b.digest(benchmark / row["path"]) != row["content_sha256"]:
            raise ValueError("Promoted Epinions SQL changed")
    counts = Counter(r.get("graph_dataset") for r in rows if r["family"] == "graph")
    if counts != marker()["dataset_counts"]:
        raise ValueError("Unexpected mixed Graph dataset counts")
    for path in benchmark.glob("*.txt"):
        if set(path.read_text().splitlines()).intersection(r["path"] for r in old.values()):
            raise ValueError("Replaced Bitcoin SQL remains in query list")
    restored = [old[r["graph_dataset_source_query"]] if r["query_id"] in expected else r for r in rows]
    return restored, {r["path"]: ARCHIVE / r["path"] for r in old.values()}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-sources", type=Path)
    parser.add_argument("--query-dataset", nargs=3, metavar=("CORPUS", "PATH", "DEFAULT"))
    args = parser.parse_args()
    if args.archive_sources:
        archive_sources(args.archive_sources)
    elif args.query_dataset:
        print(query_dataset(*args.query_dataset))
    else:
        parser.error("Choose --archive-sources or --query-dataset")
