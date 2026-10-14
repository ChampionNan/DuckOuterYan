"""Pinned predicate updates for two TPC-H slots; generation never reads results."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import balanced_benchmark as b

POLICY = b.ROOT / "sources/tpch_selectivity_update_20261014.json"
MARKER = "tpch_selectivity_update.json"
PIN_FIELDS = ("query_id", "path", "family", "content_sha256", "sql_fingerprint")


def policy():
    spec = json.loads(POLICY.read_text())
    entries = spec["replacements"]
    if len(entries) != 2 or {x["short_query"] for x in entries} != {"G-H-LD-03", "G-H-LD-05"}:
        raise ValueError("Expected the two approved TPC-H slots")
    return spec


def definition(entry):
    old = entry["original"]
    source = b.ROOT / entry["original_archive"]
    if b.digest(source) != old["content_sha256"]:
        raise ValueError("Archived TPC-H source changed")
    sql = source.read_text()
    if sql.count(old["selectivity_predicate"]) != 1:
        raise ValueError("Expected one TPC-H predicate")
    sql = sql.replace(old["selectivity_predicate"], entry["predicate"], 1)
    if hashlib.sha256(sql.encode()).hexdigest() != entry["content_sha256"]:
        raise ValueError("TPC-H definition does not match the pinned SQL")
    calibration = entry["calibration"]
    fraction = calibration["qualified_rows"] / calibration["rows"]
    lo, hi = float(old["target_min_fraction"]), float(old["target_max_fraction"])
    lower = fraction >= lo if old["target_min_inclusive"] == "true" else fraction > lo
    upper = fraction <= hi if old["target_max_inclusive"] == "true" else fraction < hi
    if not lower or not upper:
        raise ValueError("TPC-H predicate left its original selectivity band")
    updates = dict(selectivity_predicate=entry["predicate"], target_fraction=str(fraction),
                   calibration_rows=str(calibration["rows"]),
                   calibration_qualified_rows=str(calibration["qualified_rows"]),
                   calibration_fraction=str(fraction), calibration_in_range="true",
                   filter_design_revision=policy()["revision"],
                   content_sha256=entry["content_sha256"], sql_fingerprint=b.sql_fingerprint(sql, "tpch"))
    return updates, sql


def marker():
    spec = policy()
    return dict(revision=spec["revision"], policy_sha256=b.digest(POLICY),
                query_ids=[e["original"]["query_id"] for e in spec["replacements"]])


def apply(rows, output):
    entries = {e["original"]["query_id"]: e for e in policy()["replacements"]}
    if sum(r["query_id"] in entries for r in rows) != 2:
        raise ValueError("Missing or duplicate TPC-H replacement slot")
    updated, sqls = [], {}
    for row in rows:
        entry = entries.get(row["query_id"])
        if entry is None:
            updated.append(dict(row))
            continue
        old = entry["original"]
        if any(str(row.get(k, "")) != old[k] for k in PIN_FIELDS):
            raise ValueError("TPC-H source identity changed")
        if b.digest(output / row["path"]) != old["content_sha256"]:
            raise ValueError("TPC-H source SQL changed")
        changes, sql = definition(entry)
        updated.append(dict(row, **changes))
        sqls[row["path"]] = sql
    if len({r["sql_fingerprint"] for r in updated}) != len(rows):
        raise ValueError("TPC-H replacement duplicates an existing query")
    for name, sql in sqls.items():
        (output / name).write_text(sql)
    b.write_json(output / MARKER, marker())
    return updated


def validate(corpus, rows):
    """Restore source definitions for validation of earlier generation stages."""
    entries = {e["original"]["query_id"]: e for e in policy()["replacements"]}
    if not (corpus / MARKER).exists():
        if any(r["query_id"] in entries and r["content_sha256"] == entries[r["query_id"]]["content_sha256"]
               for r in rows):
            raise ValueError("TPC-H selectivity update marker missing")
        return rows, {}
    if json.loads((corpus / MARKER).read_text()) != marker():
        raise ValueError("TPC-H selectivity marker changed")
    restored, paths = [], {}
    for row in rows:
        entry = entries.get(row["query_id"])
        if entry is None:
            restored.append(row)
            continue
        changes, _ = definition(entry)
        if any(str(row.get(k, "")) != str(v) for k, v in changes.items()):
            raise ValueError("TPC-H selectivity metadata changed")
        if b.digest(corpus / row["path"]) != entry["content_sha256"]:
            raise ValueError("TPC-H selectivity SQL changed")
        old = entry["original"]
        restored.append(dict(row, **{k: old[k] for k in changes}))
        paths[old["path"]] = b.ROOT / entry["original_archive"]
    if len(paths) != 2:
        raise ValueError("Missing TPC-H replacement slot")
    return restored, paths


def promote(corpus):
    rows = b.validate(corpus)
    if (corpus / MARKER).exists():
        validate(corpus, rows)
        return
    original_manifest = b.digest(corpus / "manifest.csv")
    targets = {e["original"]["path"] for e in policy()["replacements"]}
    before = {str(p.relative_to(corpus)): b.digest(p) for p in corpus.glob("*/*.sql")}
    with tempfile.TemporaryDirectory(prefix="tpch-selectivity-promotion-") as temporary:
        stage = Path(temporary) / "benchmark"
        shutil.copytree(corpus, stage)
        updated = apply(rows, stage)
        b.write_csv(stage / "manifest.csv", updated, list(rows[0]))
        summary = json.loads((stage / "design_summary.json").read_text())
        summary["tpch_selectivity_update"] = marker()
        b.write_json(stage / "design_summary.json", summary)
        b.validate(stage)
        changed = {str(p.relative_to(stage)) for p in stage.rglob("*") if p.is_file()
                   and (not (corpus / p.relative_to(stage)).exists()
                        or p.read_bytes() != (corpus / p.relative_to(stage)).read_bytes())}
        if changed != targets | {"manifest.csv", "design_summary.json", MARKER}:
            raise ValueError("Unexpected files in TPC-H promotion: " + repr(changed))
        if b.digest(corpus / "manifest.csv") != original_manifest or any(
                b.digest(corpus / name) != sha for name, sha in before.items()):
            raise ValueError("Active corpus changed during staging")
        for name in sorted(changed):
            shutil.copyfile(stage / name, corpus / name)
    b.validate(corpus)
    after = {str(p.relative_to(corpus)): b.digest(p) for p in corpus.glob("*/*.sql")}
    if before.keys() != after.keys() or {k for k in before if before[k] != after[k]} != targets:
        raise ValueError("Promotion changed unrelated SQL")
    print("Updated G-H-LD-03 and G-H-LD-05; all 718 other SQL files unchanged.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args()
    if args.promote:
        promote(b.ROOT / "benchmark")
    else:
        validate(b.ROOT / "benchmark", b.validate(b.ROOT / "benchmark"))
