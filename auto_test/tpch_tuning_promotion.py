"""Frozen, reversible adoption of the 20 explicitly approved TPC-H candidates.

Generation is independent of measurements. The pinned policy discloses the
post-hoc workload selection; its historical statistics are not future targets.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import tempfile

import balanced_benchmark as b

POLICY = b.ROOT / "sources/tpch_tuning_promotion_20261013.json"
ORIGINAL_POLICY = b.ROOT / "sources/tpch_query_tuning_20261012.json"
CANDIDATES = b.ROOT / "candidates/tpch_query_tuning_20261012"
ARCHIVE_REVISION = "replaced_tpch_tuning_20261013"
ARCHIVE = b.ROOT / "revisions" / ARCHIVE_REVISION / "benchmark"
MARKER = "tpch_tuning_promotion.json"
QUERY_LIST = "tpch_tuning_promoted.txt"
PIN_FIELDS = ("query_id", "path", "family", "content_sha256", "sql_fingerprint")


def measurement_snapshot():
    """Load optional local reporting inputs, never during corpus generation."""
    default = b.legacy.REPO_ROOT / "auto_test/results/frozen_inputs/tpch_measurement_snapshot.json"
    path = Path(os.environ.get("OY_MEASUREMENT_SNAPSHOT", str(default)))
    if not path.is_file():
        raise FileNotFoundError(
            "Historical reporting inputs are not distributed. Set OY_MEASUREMENT_SNAPSHOT "
            "to a local snapshot file, or report a new run with gen_experiment_result.py.")
    return json.loads(path.read_text())


def policy():
    spec = json.loads(POLICY.read_text())
    if len(spec["selected_slots"]) != 20 or len(set(spec["selected_slots"])) != 20:
        raise ValueError("Expected 20 unique frozen TPC-H slots")
    return spec


def replacements():
    spec = policy()
    for name, key in (("manifest.csv", "candidate_manifest_sha256"),
                      ("replacement_map.csv", "replacement_map_sha256")):
        if b.digest(CANDIDATES / name) != spec[key]:
            raise ValueError("TPC-H candidate metadata changed: " + name)
    rows = b.read_manifest(CANDIDATES / "manifest.csv")
    by_query = {r["query_id"]: r for r in rows}
    chosen = [r for r in b.read_manifest(CANDIDATES / "replacement_map.csv")
              if r["short_query"] in spec["selected_slots"]]
    if Counter(r["change"] for r in chosen) != spec["selected_changes"]:
        raise ValueError("TPC-H frozen selection changed")
    original = {r["original"]["query_id"]: r["original"]
                for r in json.loads(ORIGINAL_POLICY.read_text())["replacements"]}
    result = []
    for entry in chosen:
        row = dict(by_query[entry["proposed_query"]])
        old = original[entry["original_query"]]
        if (row["family"] != "tpch" or row["tuning_replaces_query_id"] != old["query_id"]
                or row["tuning_replaces_sha256"] != old["content_sha256"]):
            raise ValueError("TPC-H source identity changed")
        if Path(row["path"]).parts != ("tpch", row["query_id"] + ".sql"):
            raise ValueError("Unsafe TPC-H candidate path")
        if b.digest(CANDIDATES / row["path"]) != row["content_sha256"]:
            raise ValueError("TPC-H candidate SQL changed")
        row["tpch_promotion_revision"] = spec["revision"]
        result.append(row)
    if len(result) != 20 or len({r["sql_fingerprint"] for r in result}) != 20:
        raise ValueError("Missing or duplicate TPC-H candidates")
    return result


def marker():
    spec = policy()
    return dict(revision=spec["revision"], policy_sha256=b.digest(POLICY),
                replaced_queries=20, selected_slots=spec["selected_slots"],
                selection_disclosure=spec["selection_disclosure"],
                generation_rule=spec["generation_rule"])


def archived_rows():
    rows = b.read_manifest(ARCHIVE / "manifest.csv")
    expected = {r["tuning_replaces_query_id"]: r["tuning_replaces_sha256"] for r in replacements()}
    if len(rows) != 20 or {r["query_id"] for r in rows} != set(expected):
        raise ValueError("Incomplete TPC-H source archive")
    for row in rows:
        if (row["content_sha256"] != expected[row["query_id"]]
                or b.digest(ARCHIVE / row["path"]) != row["content_sha256"]):
            raise ValueError("TPC-H source archive changed")
    return rows


def archive_sources(corpus):
    """Archive exact source definitions before replacing any active SQL."""
    if b.digest(corpus / "manifest.csv") != policy()["prior_manifest_sha256"]:
        raise ValueError("Active manifest changed before TPC-H promotion")
    rows = b.read_manifest(corpus / "manifest.csv")
    expected = {r["tuning_replaces_query_id"]: r["tuning_replaces_sha256"] for r in replacements()}
    selected = [r for r in rows if r["query_id"] in expected]
    if len(selected) != 20:
        raise ValueError("TPC-H sources missing before archive")
    for row in selected:
        target = ARCHIVE / row["path"]
        if b.digest(corpus / row["path"]) != expected[row["query_id"]]:
            raise ValueError("Locally edited TPC-H source")
        if target.exists() and b.digest(target) != row["content_sha256"]:
            raise ValueError("Refusing to overwrite changed TPC-H archive")
    if (ARCHIVE / "manifest.csv").exists():
        if b.read_manifest(ARCHIVE / "manifest.csv") != selected:
            raise ValueError("TPC-H archive manifest changed")
    prior = ARCHIVE / "prior_manifest.csv"
    if prior.exists() and b.digest(prior) != policy()["prior_manifest_sha256"]:
        raise ValueError("TPC-H prior full manifest changed")
    for row in selected:
        target = ARCHIVE / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(corpus / row["path"], target)
    b.write_csv(ARCHIVE / "manifest.csv", selected)
    shutil.copyfile(corpus / "manifest.csv", prior)
    return archived_rows()


def apply(records, output):
    """Apply pinned definitions to a generation staging directory."""
    targets = {r["tuning_replaces_query_id"]: r for r in replacements()}
    archived = {r["query_id"]: r for r in archived_rows()}
    originals = [r for r in records if r["query_id"] in targets]
    if len(originals) != 20:
        raise ValueError("Missing or duplicate TPC-H promotion source")
    path_map = {}
    for old in originals:
        new = targets[old["query_id"]]
        if any(str(old[k]) != archived[old["query_id"]][k] for k in PIN_FIELDS):
            raise ValueError("Generated TPC-H source identity changed")
        if b.digest(output / old["path"]) != old["content_sha256"]:
            raise ValueError("Generated TPC-H SQL changed")
        if (output / new["path"]).exists():
            raise ValueError("TPC-H replacement path already exists")
        for key in ("tree_shape", "semantic_tier", "relation_count", "query_class", "source_seed"):
            if str(old[key]) != str(new[key]):
                raise ValueError("TPC-H replacement changed its slot: " + key)
        path_map[old["path"]] = new["path"]
    updated = [dict(targets.get(r["query_id"], r)) for r in records]
    for key in ("query_id", "path", "sql_fingerprint"):
        if len({r[key] for r in updated}) != len(records):
            raise ValueError("TPC-H promotion introduced duplicate " + key)
    for old in originals:
        new = targets[old["query_id"]]
        shutil.copyfile(CANDIDATES / new["path"], output / new["path"])
        (output / old["path"]).unlink()  # Verified staging copy; original is archived.
    for path in output.glob("*.txt"):
        text = path.read_text()
        replaced = "".join(path_map.get(line, line) + "\n" for line in text.splitlines())
        if replaced != text:
            path.write_text(replaced)
    (output / QUERY_LIST).write_text("".join(r["path"] + "\n" for r in replacements()))
    b.write_json(output / MARKER, marker())
    return updated


def validate(corpus, rows):
    """Restore prior metadata/paths for validation of earlier generator stages."""
    expected = {r["query_id"]: r for r in replacements()}
    if not (corpus / MARKER).exists():
        if any(r["query_id"] in expected or r.get("tpch_promotion_revision") for r in rows):
            raise ValueError("TPC-H promotion marker missing")
        return rows, {}, {}
    if json.loads((corpus / MARKER).read_text()) != marker():
        raise ValueError("TPC-H promotion marker changed")
    old = {r["query_id"]: r for r in archived_rows()}
    ids = {r["query_id"] for r in rows}
    if not set(expected).issubset(ids) or set(old).intersection(ids):
        raise ValueError("Missing TPC-H replacement or original still active")
    if Counter(r["family"] for r in rows) != policy()["expected_counts"]:
        raise ValueError("TPC-H promotion changed family counts")
    actual = [r for r in rows if r["query_id"] in expected]
    for row in actual:
        if any(str(row.get(k, "")) != v for k, v in expected[row["query_id"]].items()):
            raise ValueError("Promoted TPC-H metadata changed")
        if b.digest(corpus / row["path"]) != row["content_sha256"]:
            raise ValueError("Promoted TPC-H SQL changed")
    old_paths = {r["path"]: ARCHIVE / r["path"] for r in old.values()}
    if any((corpus / p).exists() for p in old_paths):
        raise ValueError("Original TPC-H SQL still active")
    for path in corpus.glob("*.txt"):
        if set(path.read_text().splitlines()).intersection(old_paths):
            raise ValueError("Original TPC-H SQL remains in query list")
    if (corpus / QUERY_LIST).read_text().splitlines() != [r["path"] for r in replacements()]:
        raise ValueError("TPC-H promoted query list changed")
    restored = [old[r["tuning_replaces_query_id"]] if r["query_id"] in expected else r for r in rows]
    path_map = {old[r["tuning_replaces_query_id"]]["path"]: r["path"] for r in actual}
    return restored, old_paths, path_map


def promote(corpus):
    """Publish only the reviewed TPC-H changes after validating a staged corpus."""
    rows = b.validate(corpus)
    if (corpus / MARKER).exists():
        validate(corpus, rows)
        print("The 20-query TPC-H setting is already fixed.")
        return
    archive_sources(corpus)
    with tempfile.TemporaryDirectory(prefix="tpch-promotion-") as tmp:
        stage = Path(tmp) / "benchmark"
        shutil.copytree(corpus, stage)
        updated = sorted(apply(rows, stage), key=lambda r: r["path"])
        # Reuse generator field order so clean regeneration is byte-identical.
        fields = list(b.read_manifest(CANDIDATES / "proposed_full_manifest.csv")[0])
        fields.append("tpch_promotion_revision")
        b.write_csv(stage / "manifest.csv", updated, fields)
        summary = json.loads((stage / "design_summary.json").read_text())
        summary["tpch_tuning_promotion"] = marker()
        b.write_json(stage / "design_summary.json", summary)
        b.validate(stage)
        for source in stage.rglob("*"):
            if not source.is_file():
                continue
            target = corpus / source.relative_to(stage)
            if not target.exists() or source.read_bytes() != target.read_bytes():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        for old in archived_rows():
            target = corpus / old["path"]
            if b.digest(target) != old["content_sha256"]:
                raise ValueError("Source changed while publishing TPC-H promotion")
            target.unlink()
    b.validate(corpus)
    print("Fixed 20 TPC-H replacements; 720 queries remain. Old SQL is recoverable at " + str(ARCHIVE))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.promote:
        promote(b.ROOT / "benchmark")
    elif args.validate:
        validate(b.ROOT / "benchmark", b.validate(b.ROOT / "benchmark"))
        print("TPC-H promotion validated.")
    else:
        parser.error("Choose --promote or --validate")
