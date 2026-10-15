"""Pinned predicate-only replacements after workload membership selection.

Generation reads definitions, never measurements. Historical reports explicitly
map source observations to the promoted SQL; only comments may differ between
the measured candidate and its promoted SQL text.
"""
import hashlib
import json

import balanced_benchmark as b


POLICY = b.ROOT / "sources/cohort_selectivity_20261015.json"
REVISION = "cohort-selectivity-20261015"
SOURCE = b.ROOT / "revisions/pre_plan_cohort_20261014/benchmark"
BANDS = {"low": (0, .05, "false", "false"),
         "medium": (.05, .4, "true", "false"),
         "high": (.4, .6, "true", "true")}


def policy():
    spec = json.loads(POLICY.read_text())
    if spec["revision"] != REVISION or len(spec["replacements"]) != 2:
        raise ValueError("Expected the two approved predicate replacements")
    for field in ("original_query", "query_id"):
        if len({entry[field] for entry in spec["replacements"]}) != 2:
            raise ValueError("Duplicate predicate replacement")
    return spec


def definition(old, entry):
    if old["query_id"] != entry["original_query"] or old["content_sha256"] != entry["original_sha256"]:
        raise ValueError("Predicate replacement source identity changed")
    source = SOURCE / old["path"]
    if b.digest(source) != entry["original_sha256"]:
        raise ValueError("Archived predicate replacement SQL changed")
    sql = source.read_text()
    if sql.count(old["selectivity_predicate"]) != 1:
        raise ValueError("Expected exactly one source predicate")
    measured = sql.replace(old["selectivity_predicate"], entry["predicate"], 1)
    if hashlib.sha256(measured.encode()).hexdigest() != entry["measurement_content_sha256"]:
        raise ValueError("Measured predicate-only candidate identity changed")
    tier = entry["semantic_tier"]
    sql = measured.replace("-- selectivity: " + old["semantic_tier"] + ";",
                           "-- selectivity: " + tier + ";", 1)
    sha = hashlib.sha256(sql.encode()).hexdigest()
    fingerprint = b.sql_fingerprint(sql, old["family"])
    if sha != entry["content_sha256"] or fingerprint != b.sql_fingerprint(measured, old["family"]):
        raise ValueError("Promoted SQL changed beyond its selectivity comment")
    lo, hi, lower_closed, upper_closed = BANDS[tier]
    calibration = entry["calibration"]
    fraction = calibration["qualified_rows"] / calibration["rows"]
    lower = fraction >= lo if lower_closed == "true" else fraction > lo
    upper = fraction <= hi if upper_closed == "true" else fraction < hi
    if not lower or not upper:
        raise ValueError("Replacement selectivity does not match its tier")
    query = entry["query_id"]
    if query != old["query_id"].replace("__sel_" + old["semantic_tier"] + "__", "__sel_" + tier + "__"):
        raise ValueError("Replacement query name does not match its tier")
    row = dict(old, query_id=query, path=old["family"] + "/" + query + ".sql",
               content_sha256=sha, sql_fingerprint=fingerprint,
               filter_design_revision=REVISION, selectivity_predicate=entry["predicate"],
               semantic_tier=tier, selectivity_tier="sel_" + tier,
               target_min_fraction=str(lo), target_max_fraction=str(hi),
               target_min_inclusive=lower_closed, target_max_inclusive=upper_closed,
               target_fraction=str(fraction), calibration_fraction=str(fraction),
               calibration_rows=str(calibration["rows"]),
               calibration_qualified_rows=str(calibration["qualified_rows"]), calibration_in_range="true",
               replaces_query_id=old["query_id"], replaces_content_sha256=old["content_sha256"],
               parameter_policy="Frozen predicate-only replacement selected after CPU9 pilot; "
                                "generation never reads timings; no future speedup guarantee.")
    return row, sql


def transform(rows):
    entries = {entry["original_query"]: entry for entry in policy()["replacements"]}
    expected_updates = set(entries) & {row["query_id"] for row in rows}
    updated, sqls, paths = [], {}, {}
    for row in rows:
        entry = entries.get(row["query_id"])
        if entry is None:
            updated.append(dict(row))
            continue
        new, sql = definition(row, entry)
        updated.append(new)
        sqls[new["path"]] = sql
        paths[row["path"]] = new["path"]
    if len(paths) != len(expected_updates) or len({r["sql_fingerprint"] for r in updated}) != len(updated):
        raise ValueError("Missing or duplicate promoted SQL")
    return updated, sqls, paths


def members(spec):
    entries = {entry["original_query"]: entry for entry in policy()["replacements"]}
    old_rows = {row["query_id"]: row for row in b.read_manifest(SOURCE / "manifest.csv")}
    result = []
    for member in spec["members"]:
        entry = entries.get(member["query_id"])
        if entry is None or member["role"] == "removed":
            result.append(dict(member, measurement_content_sha256=""))
            continue
        if member["role"] != "selected":
            raise ValueError("Only a selected query may be replaced")
        row, _ = definition(old_rows[member["query_id"]], entry)
        result.append(dict(member, **{key: row[key] for key in (
            "query_id", "path", "content_sha256", "sql_fingerprint")},
            decision_source=entry["measurement_csv"], decision_query=entry["measurement_query"],
            measurement_content_sha256=entry["measurement_content_sha256"],
            reference_decision_reason=entry["decision_reason"]))
    return result


def source_files():
    return [dict(path=path, sha256=sha) for path, sha in sorted({
        (entry["measurement_csv"], entry["measurement_csv_sha256"]) for entry in policy()["replacements"]})]


def marker():
    return dict(revision=REVISION, policy_sha256=b.digest(POLICY),
                query_ids=[entry["query_id"] for entry in policy()["replacements"]])
