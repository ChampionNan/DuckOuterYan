#!/usr/bin/env python3
"""Prepare a separate, dataset-qualified retest of pinned short Graph queries.

The active Bitcoin corpus and historical results are never edited. Calibration
uses base-table counts only, before any target-dataset performance measurement.
"""
import argparse
import csv
import hashlib
import json
import socket
import subprocess
from pathlib import Path

from benchmark_corpus import count_base_relations, read_manifest, sql_fingerprint

SCRIPT = Path(__file__).resolve().parent
ROOT = SCRIPT / "outerjoin_benchmark"
POLICY = ROOT / "sources/graph_dataset_retest_20261010.json"
DESIGN = ROOT / "sources/balanced_design.json"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def content_hash(sql):
    return hashlib.sha256(sql.encode()).hexdigest()


def load_policy(path=POLICY):
    from workload_policy import validate_pins

    spec = json.loads(Path(path).read_text())
    pins = validate_pins(spec, "replacements")
    if len(pins) != spec["expected_queries"] or spec["target_dataset"] != "epinions":
        raise ValueError("Unexpected Graph retest policy")
    for field in ("query_id", "path", "sql_fingerprint"):
        if len({r[field] for r in pins}) != len(pins):
            raise ValueError("Duplicate Graph retest " + field)
    for row in pins:
        if row["family"] != "graph" or row["semantic_tier"] not in ("low", "medium"):
            raise ValueError("Invalid frozen Graph query definition")
        path = Path(row["path"])
        if path.parts != ("graph", row["query_id"] + ".sql"):
            raise ValueError("Unsafe Graph SQL path")
    return spec


def sql_json(binary, database, sql):
    result = subprocess.run(
        [str(binary), "-readonly", "-no-init", "-bail", "-json", str(database), "-c",
         "SET disabled_optimizers='outer_yan'; SET threads=4; " + sql],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
        check=True, timeout=60)
    return json.loads(result.stdout)


def identity(binary, database, relation):
    if relation not in {"R" + str(i) for i in range(1, 6)}:
        raise ValueError("Unexpected calibration relation")
    return sql_json(binary, database,
                    "SELECT count(*) AS n, sum(src)::VARCHAR AS sum_src, "
                    "sum(dst)::VARCHAR AS sum_dst, count(DISTINCT src) AS source_vertices, "
                    "count(DISTINCT dst) AS destination_vertices FROM " + relation + ";")[0]


def in_band(fraction, band):
    lower = fraction >= band["lower_bound"] if band["include_lower"] else fraction > band["lower_bound"]
    upper = fraction <= band["upper_bound"] if band["include_upper"] else fraction < band["upper_bound"]
    return lower and upper


def calibrate(binary, database, spec, design):
    """Nearest cumulative source-ID threshold; ties choose the lower threshold."""
    database = Path(database).resolve(strict=True)
    stat = database.stat()
    measured_identity = identity(binary, database, "R1")
    if measured_identity != spec["dataset_identity"]:
        raise ValueError("Database does not match the pinned Epinions base-table counts")
    profiles = {}
    for role, profile_id in (("anchor", "graph_source_range"), ("auxiliary", "graph_aux_source_range")):
        original = design["profiles"][profile_id]
        bands = original.get("tiers", design["tiers"])
        for tier in sorted({r["semantic_tier"] for r in spec["replacements"]}):
            band = next(b for b in bands if b["name"] == tier)
            target = float(band["target_fraction"])
            sql = ("WITH counts AS (SELECT src,count(*) n FROM R1 GROUP BY src), "
                   "cumulative AS (SELECT src,sum(n) OVER (ORDER BY src) c FROM counts) "
                   "SELECT src AS threshold,c::BIGINT AS qualified FROM cumulative "
                   "ORDER BY abs(c::DOUBLE / " + str(measured_identity["n"]) + " - " + repr(target) + "),src LIMIT 1;")
            value = sql_json(binary, database, sql)[0]
            fraction = value["qualified"] / measured_identity["n"]
            if not in_band(fraction, band):
                raise ValueError("No suitable source-ID threshold for " + role + "/" + tier)
            profiles[role + "/" + tier] = dict(
                threshold=int(value["threshold"]), qualified_rows=value["qualified"],
                total_rows=measured_identity["n"], observed_fraction=fraction, band=band)
    # Audit every graph alias copy, not merely R1; these tables must share data.
    for relation in ("R2", "R3", "R4", "R5"):
        if identity(binary, database, relation) != measured_identity:
            raise ValueError("Graph relation differs from R1: " + relation)
        for tier in ("low", "medium"):
            profile = profiles["auxiliary/" + tier]
            count = sql_json(binary, database, "SELECT count(*) AS n FROM " + relation +
                             " WHERE src <= " + str(profile["threshold"]) + ";")[0]["n"]
            if count != profile["qualified_rows"]:
                raise ValueError("Input predicate calibration differs: " + relation)
    after = database.stat()
    if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Database changed during calibration")
    return dict(dataset=spec["target_dataset"], database=str(database),
                database_size_bytes=stat.st_size, database_mtime_ns=stat.st_mtime_ns,
                execution_host=socket.gethostname(), table_identity=measured_identity,
                profiles=profiles, all_input_predicates_audited=True,
                calibration_method="Nearest cumulative edge fraction over ordered source IDs; no timing or speed-up used")


def replace_once(sql, old, new):
    if sql.count(old) != 1:
        raise ValueError("Expected exactly one pinned predicate: " + old)
    return sql.replace(old, new, 1)


def transform(row, sql, pin, spec, audit):
    for key in ("query_id", "path", "family", "content_sha256", "sql_fingerprint", "semantic_tier", "relation_count"):
        if str(row.get(key, "")) != str(pin[key]):
            raise ValueError("Pinned Graph metadata changed: " + key)
    if content_hash(sql) != pin["content_sha256"] or sql_fingerprint(sql, "graph") != pin["sql_fingerprint"]:
        raise ValueError("Pinned Graph SQL changed")
    tier = row["semantic_tier"]
    primary = audit["profiles"]["anchor/" + tier]
    auxiliary = audit["profiles"]["auxiliary/" + tier]
    predicate = "R1.src <= " + str(primary["threshold"])
    result = replace_once(sql, row["selectivity_predicate"], predicate)
    old_filters = json.loads(row["input_filter_profiles_json"])
    expected_aliases = {"R" + str(i) for i in range(2, int(row["relation_count"]) + 1)}
    if {f["relation"] for f in old_filters} != expected_aliases or len(old_filters) != len(expected_aliases):
        raise ValueError("Missing or repeated graph input cap")
    filters = []
    for extra in old_filters:
        alias = extra["relation"]
        old = "(SELECT src, dst FROM {0} WHERE {1}) {0}".format(
            alias, extra["predicate"].replace(alias + ".", ""))
        new = "(SELECT src, dst FROM {0} WHERE src <= {1}) {0}".format(alias, auxiliary["threshold"])
        result = replace_once(result, old, new)
        filters.append(dict(relation=alias, profile="graph_epinions_aux_source_range",
                            predicate=alias + ".src <= " + str(auxiliary["threshold"]),
                            calibration_fraction=auxiliary["observed_fraction"]))
    # All changed substrings above are filter predicates. Projection, join kinds,
    # ON keys, grouping and aggregate expression remain byte-for-byte unchanged.
    if count_base_relations(result) != int(row["relation_count"]):
        raise ValueError("Graph relation count changed")
    query = row["query_id"].replace("__graph__", "__graph__epinions__", 1)
    result = ("-- graph_dataset: epinions; replaces Bitcoin instance: " + row["query_id"] + "\n" + result)
    updated = dict(row, query_id=query, path="graph/" + query + ".sql", graph_dataset="epinions",
                   graph_dataset_revision=spec["revision"], graph_dataset_source_query=row["query_id"],
                   graph_dataset_source_sha256=row["content_sha256"],
                   selectivity_profile="graph_epinions_source_range", selectivity_predicate=predicate,
                   calibration_rows=primary["total_rows"], calibration_qualified_rows=primary["qualified_rows"],
                   calibration_fraction=primary["observed_fraction"], calibration_in_range="true",
                   input_filter_profiles_json=json.dumps(filters, separators=(",", ":")),
                   parameter_policy="Dataset-recalibrated source-ID ranges; same selectivity bands; target-server retest required",
                   qualification_status="PENDING_CPU9_MEASUREMENT",
                   sql_fingerprint=sql_fingerprint(result, "graph"), content_sha256=content_hash(result))
    return updated, result


def prepare(corpus, output, binary, database, policy_path=POLICY):
    spec = load_policy(policy_path)
    design = json.loads(DESIGN.read_text())
    corpus, output = Path(corpus).resolve(), Path(output).resolve()
    if output == corpus or corpus in output.parents or output in corpus.parents:
        raise ValueError("Retest output must be separate from the active corpus")
    rows = {r["query_id"]: r for r in read_manifest(corpus / "manifest.csv")}
    sources = []
    archived_sources = {}
    import graph_dataset_promotion
    import graph_dataset_extension
    retired = {graph_dataset_promotion.RETIRED_QUERY} | graph_dataset_extension.retired_queries()
    for stage in (graph_dataset_promotion, graph_dataset_extension):
        if (corpus / stage.MARKER).exists():
            replacements = {r["graph_dataset_source_query"]: r for r in stage.candidates()}
            for row in stage.archived_rows():
                archived_sources[row["query_id"]] = (row, stage.ARCHIVE, replacements[row["query_id"]])
    for pin in spec["replacements"]:
        row = rows.get(pin["query_id"])
        archived = archived_sources.get(pin["query_id"])
        source_path = corpus / pin["path"]
        if row is None and archived:
            row, archive, replacement = archived
            source_path = archive / pin["path"]
            if replacement["query_id"] not in retired:
                if (replacement["query_id"] not in rows or
                        digest(corpus / replacement["path"]) != replacement["content_sha256"]):
                    raise ValueError("Promoted Graph query has changed")
        if row is None:
            raise ValueError("Missing pinned Graph query: " + pin["query_id"])
        sql = source_path.read_text()
        if content_hash(sql) != pin["content_sha256"]:
            raise ValueError("Source query was edited: " + pin["path"])
        sources.append((row, sql, pin))
    audit = calibrate(binary, database, spec, design)
    candidates = [transform(row, sql, pin, spec, audit) for row, sql, pin in sources]
    for key in ("query_id", "path", "sql_fingerprint"):
        if len({r[key] for r, _ in candidates}) != len(candidates):
            raise ValueError("Duplicate retest identity: " + key)
    audit.update(policy_sha256=digest(policy_path), source_manifest_sha256=digest(corpus / "manifest.csv"),
                 candidate_count=len(candidates), revision=spec["revision"],
                 status="PENDING_CPU9_MEASUREMENT", replaces_only=[r["query_id"] for r, _, _ in sources])
    files = {r["path"]: sql for r, sql in candidates}
    files["query_list.txt"] = "".join(r["path"] + "\n" for r, _ in candidates)
    # Refuse unfamiliar/modified files on a rerun, including an altered manifest.
    if output.exists():
        expected_paths = set(files) | {"manifest.csv"}
        present = {str(p.relative_to(output)) for p in output.rglob("*") if p.is_file()}
        # The audit records host-specific paths/signatures and is not committed.
        # A freshly pulled candidate corpus therefore does not contain it yet.
        if present - {"dataset_audit.json"} != expected_paths:
            raise ValueError("Retest output is not an exact previous generated corpus")
        for name, content in files.items():
            if (output / name).read_text() != content:
                raise ValueError("Refusing to overwrite changed retest SQL/list: " + name)
        previous = read_manifest(output / "manifest.csv")
        expected = [{k: str(v) for k, v in r.items()} for r, _ in candidates]
        if previous != expected:
            raise ValueError("Refusing to overwrite changed retest manifest")
    output.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    with (output / "manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(candidates[0][0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(r for r, _ in candidates)
    (output / "dataset_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print("Prepared {} Epinions queries at {} (Bitcoin corpus unchanged)".format(len(candidates), output))
    for name, profile in audit["profiles"].items():
        print("{}: src <= {}, {:.4%}".format(name, profile["threshold"], profile["observed_fraction"]))
    return candidates, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "benchmark")
    parser.add_argument("--output", type=Path, default=ROOT / "graph_dataset_retest/epinions")
    parser.add_argument("--duckdb", type=Path, default=SCRIPT.parent / "build/release/duckdb")
    parser.add_argument("--database", type=Path, default=SCRIPT.parent / "graph_epinions.duckdb")
    parser.add_argument("--policy", type=Path, default=POLICY)
    args = parser.parse_args()
    prepare(args.corpus, args.output, args.duckdb, args.database, args.policy)


if __name__ == "__main__":
    main()
