"""Pinned, exact-SQL performance exclusions for the primary benchmark batch."""
from collections import Counter
import json
import math

import balanced_benchmark as b
from workload_policy import validate_pins

POLICY = b.ROOT / "sources/speedup_screen_20261008.json"
MARKER = "speedup_screen.json"


def below_threshold(result, threshold=.5, *, inclusive=False, allow_unchecked=False):
    """Compare complete measurements, without mistaking disabled checks for proof."""
    correctness_eligible = result.get("correct") == "TRUE" or (
        allow_unchecked and result.get("correct") == "NOT-CHECKED"
        and result.get("correctness_check") == "disabled")
    if not correctness_eligible or result.get("timing_status") != "measured":
        return False
    try:
        off, on = float(result["tm_off"]), float(result["tm_on"])
    except (KeyError, TypeError, ValueError):
        return False
    if not all(math.isfinite(t) and t > 0 for t in (off, on)):
        return False
    return off / on <= threshold if inclusive else off / on < threshold


def policy():
    spec = json.loads(POLICY.read_text(encoding="utf-8"))
    for row in validate_pins(spec):
        rule_id = row.get("screen_rule")
        rule = spec.get("rules", {}).get(rule_id) if rule_id else None
        if rule_id and (rule is None or row["family"] not in rule["families"]
                        or row["measurement_source"] != rule["measurement_source"]):
            raise ValueError(f"Invalid scoped speed-up rule: {row['query_id']}")
    return spec


def apply(records, output):
    """Screen generated SQL without reading or modifying raw experiment CSVs."""
    spec = policy()
    if dict(Counter(r["family"] for r in records)) != spec["expected_counts_before"]:
        raise ValueError("Speed-up screen no longer matches the pinned primary batch")
    excluded = {r["sql_fingerprint"]: r for r in spec["excluded"]}
    retained, removed = [], []
    for row in records:
        match = excluded.get(row["sql_fingerprint"])
        if match:
            if any(str(row[k]) != str(match[k]) for k in
                   ("query_id", "family", "path", "content_sha256")):
                raise ValueError(f"Speed-up exclusion changed: {row['query_id']}")
            (output / row["path"]).unlink()  # Only staged, newly generated SQL.
            # Retain the original generated metadata so earlier quota checks can
            # reconstruct recovery triples without restoring them to the corpus.
            removed.append(dict(row, **match))
        else:
            row["qualification_min_speedup"] = spec["minimum_speedup"]
            retained.append(row)
    if len(removed) != len(excluded):
        raise ValueError("Incomplete exact-SQL speed-up exclusion set")
    # Explicit query-list runs must not retain paths removed from the manifest.
    recovery_list = output / "tpcds_recovery.txt"
    if recovery_list.exists():
        active_paths = {row["path"] for row in retained}
        recovery_list.write_text("".join(path + "\n" for path in recovery_list.read_text().splitlines()
                                         if path in active_paths), encoding="utf-8")
    b.write_csv(output / "speedup_excluded.csv", removed)
    b.write_json(output / MARKER, dict(
        revision=spec["revision"], policy_sha256=b.digest(POLICY),
        source=spec["source"], source_sha256=spec["source_sha256"],
        evidence_sources=spec["evidence_sources"],
        rules=spec.get("rules", {}),
        rule_removed_counts={rule: dict(Counter(row["family"] for row in removed
                                               if row.get("screen_rule") == rule))
                             for rule in spec.get("rules", {})},
        removed_queries=len(removed), previously_retired_tpcds_queries=len(spec["previously_retired_tpcds_queries"]),
        counts=dict(Counter(r["family"] for r in retained)),
        minimum_speedup=spec["minimum_speedup"],
        note="Frozen exact-SQL exclusions, not dynamic screening of new results. New Graph/JOB evidence has correctness checks disabled. No extra timeout/fallback removal; pending candidates are not measured results."))
    return retained


def validate(benchmark, rows):
    """Validate the screen, then reconstruct pre-screen quotas for earlier checks."""
    spec = policy()
    marker = json.loads((benchmark / MARKER).read_text(encoding="utf-8"))
    if marker["revision"] != spec["revision"] or marker["policy_sha256"] != b.digest(POLICY):
        raise ValueError("Speed-up screening policy changed; regenerate")
    if marker.get("rules", {}) != spec.get("rules", {}):
        raise ValueError("Scoped speed-up screening rules changed; regenerate")
    rule_counts = {rule: dict(Counter(row["family"] for row in spec["excluded"]
                                     if row.get("screen_rule") == rule))
                   for rule in spec.get("rules", {})}
    if marker.get("rule_removed_counts", {}) != rule_counts:
        raise ValueError("Scoped speed-up exclusion counts changed; regenerate")
    counts = dict(Counter(r["family"] for r in rows))
    if counts != spec["expected_counts_after"] or marker["counts"] != counts:
        raise ValueError("Speed-up screen counts do not match the pinned design")
    excluded = {r["sql_fingerprint"] for r in spec["excluded"]}
    if any(r["sql_fingerprint"] in excluded for r in rows):
        raise ValueError("An excluded slow SQL query was restored")
    if any(float(r["qualification_min_speedup"]) != spec["minimum_speedup"] for r in rows):
        raise ValueError("Inconsistent primary-batch speed-up qualification threshold")
    removed = b.read_manifest(benchmark / "speedup_excluded.csv")
    by_fingerprint = {r["sql_fingerprint"]: r for r in removed}
    if len(removed) != len(excluded) or set(by_fingerprint) != excluded:
        raise ValueError("Incomplete excluded-query metadata for quota validation")
    for evidence in spec["excluded"]:
        row = by_fingerprint[evidence["sql_fingerprint"]]
        if any(key in row for key in ("duckdb_s", "outeryan_s", "speedup", "tm_off", "tm_on")):
            raise ValueError("Excluded-query evidence changed: measurements are not workload metadata")
        if any(str(row.get(key, "")) != str(value) for key, value in evidence.items()):
            raise ValueError(f"Excluded-query evidence changed: {evidence['query_id']}")
    return rows + removed
