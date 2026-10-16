"""Frozen plan-selection cohort; keep SQL recoverable and generation result-free.

Generation applies pinned membership without reading measurements and
never promotes an unmeasured candidate or treats a fallback's 1x as a timing.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json

import balanced_benchmark as b
import cohort_query_updates as query_updates
from workload_policy import validate_pins


REVISION = "selected-plus-cost-controls-20261014"
POLICY = b.ROOT / "sources/plan_cohort_20261014.json"
ARCHIVE = b.ROOT / "revisions/pre_plan_cohort_20261014/benchmark"
MARKER = "plan_cohort.json"
MEMBERSHIP = "plan_cohort.csv"
PIN_FIELDS = ("query_id", "family", "path", "content_sha256", "sql_fingerprint")
INITIAL_CONTROL_COUNT = 65
CONTROL_COUNT = 39
DEDUP_REVISION = "tpcds-control-pattern-shape-20261015"
DEDUP_REMOVAL_REASON = "duplicate_tpcds_control_pattern_shape"
RETIRED_BOTH_TIMEOUTS = 21
RETIRED_JOB_QUERY = "aggregate__job__job_10a_cast_credits__right_deep__rlif__87f83502__sel_medium__grouped_count"
JOB_RETIREMENT_REASON = "user_requested_speedup_below_0_7"
RETIRED_FAMILY_MINIMA = {
    "graph__tpch__th_real_custdist__left_deep__lrf__65a983cc__sel_high",
    "aggregate__job__sqlstorm_job_11914__bushy__ilrff__9a0ef4e8__sel_high__grouped_count",
}
FAMILY_MINIMUM_RETIREMENT_REASON = "user_requested_family_minimum_20261015"
REPORTING_RULE = dict(fallback_speedup=1.0, duckdb_only_timeout_seconds=600,
                      outeryan_timeout="exclude", both_timeout="remove_from_benchmark",
                      raw_measurements="preserve", capped_speedup="timeout_limit_proxy_not_measured")


def policy():
    spec = json.loads(POLICY.read_text())
    validate_pins(spec, "members")
    if len(spec["members"]) != 720 or len({r["query_id"] for r in spec["members"]}) != 720:
        raise ValueError("Expected the complete 720-query source cohort")
    roles = Counter(r["role"] for r in spec["members"])
    if roles != {"selected": 282, "cost_control": CONTROL_COUNT, "removed": 399}:
        raise ValueError("Cohort role counts changed")
    if sum(r["role"] != "removed" for r in spec["members"]) != 321:
        raise ValueError("Cohort membership changed")
    retired_job = [r for r in spec["members"] if r["removal_reason"] == JOB_RETIREMENT_REASON]
    if len(retired_job) != 1 or retired_job[0]["query_id"] != RETIRED_JOB_QUERY or retired_job[0]["role"] != "removed":
        raise ValueError("Exact JOB retirement changed")
    retired_minima = [r for r in spec["members"]
                      if r["removal_reason"] == FAMILY_MINIMUM_RETIREMENT_REASON]
    if ({r["query_id"] for r in retired_minima} != RETIRED_FAMILY_MINIMA
            or any(r["role"] != "removed" for r in retired_minima)):
        raise ValueError("Exact TPC-H/JOB minimum retirements changed")
    if spec.get("control_deduplication", {}).get("revision") != DEDUP_REVISION:
        raise ValueError("TPC-DS control deduplication policy changed")
    if sum(r["removal_reason"] == DEDUP_REMOVAL_REASON for r in spec["members"]) != 26:
        raise ValueError("TPC-DS duplicate control retirements changed")
    if sum(r["removal_reason"] == "both_engines_timeout" for r in spec["members"]) != RETIRED_BOTH_TIMEOUTS:
        raise ValueError("Both-timeout retirements changed")
    if spec.get("reporting_rule") != REPORTING_RULE:
        raise ValueError("Cohort reporting rule changed")
    return spec


def input_corpus():
    """The complete predecessor, for historical transformation tests."""
    return ARCHIVE if ARCHIVE.exists() else b.ROOT / "benchmark"


def identity(row):
    return {k: row[k] for k in PIN_FIELDS}


def same_dependency(source, target):
    if not target.is_file():
        return False
    if source.read_bytes() == target.read_bytes():
        return True
    if source.name != "speedup_excluded.csv":
        return False
    # The earlier screen records an older synthetic-generator source revision.
    # Normalize only the pinned successor revision; all other fields must match.
    old, new = b.read_manifest(source), b.read_manifest(target)
    if len(old) != len(new):
        return False
    for expected, generated in zip(old, new):
        if (generated.get("source_location") == "auto_test/balanced_benchmark.py"
                and generated.get("source_sha256") == b.SYNTHETIC_SOURCE_SHA256):
            generated["source_sha256"] = expected["source_sha256"]
    return old == new


def choose_controls(rows, decisions, count=INITIAL_CONTROL_COUNT):
    """Water-fill family totals; balance metadata within each family, not speedup."""
    selected = [r for r in rows if decisions[r["query_id"]]["selected_plan"] == "OUTERYAN"]
    totals = Counter(r["family"] for r in selected)
    pools = {f: [r for r in rows if r["family"] == f and int(r["relation_count"]) > 3
                 and decisions[r["query_id"]]["decision_reason"] == "COST_DUCKDB_BETTER"]
             for f in b.FAMILIES}
    used = {f: Counter() for f in b.FAMILIES}
    dimensions = ("semantic_tier", "tree_shape", "source_seed", "relation_count", "query_class")
    chosen = []
    for _ in range(count):
        available = [f for f in b.FAMILIES if pools[f]]
        if not available:
            raise ValueError("Insufficient non-three-table cost controls")
        family = min(available, key=lambda f: (totals[f], b.FAMILIES.index(f)))
        def score(row):
            # Lexicographic tier/shape balancing and deterministic content tie-break.
            return tuple(used[family][(k, row[k])] for k in dimensions) + (
                hashlib.sha256((REVISION + row["query_id"]).encode()).hexdigest(),)
        row = min(pools[family], key=score)
        pools[family].remove(row)
        chosen.append(row)
        totals[family] += 1
        used[family].update((k, row[k]) for k in dimensions)
    return chosen


def deduplicate_tpcds_controls(controls):
    """Keep one control per source/shape, without inspecting timing results.

    This is workload-level deduplication, not equality of optimized join trees.
    Scarce groups are considered first; tiers are balanced with stable ID ties.
    Other families and every historically selected query remain untouched.
    """
    groups = defaultdict(list)
    retained = [row for row in controls if row["family"] != "tpcds"]
    for row in controls:
        if row["family"] == "tpcds":
            groups[(row["source_seed"], row["tree_shape"])].append(row)
    used_tiers = Counter()
    for key in sorted(groups, key=lambda key: (len(groups[key]), key)):
        row = min(groups[key], key=lambda row: (
            used_tiers[row["semantic_tier"]],
            hashlib.sha256((DEDUP_REVISION + row["query_id"]).encode()).hexdigest()))
        retained.append(row)
        used_tiers[row["semantic_tier"]] += 1
    return sorted(retained, key=lambda row: row["query_id"])


def marker(spec):
    roles = Counter(r["role"] for r in spec["members"])
    return dict(revision=spec["revision"], policy_sha256=b.digest(POLICY),
                counts=spec["expected_counts_after"], selected=roles["selected"],
                cost_controls=roles["cost_control"], removed=roles["removed"],
                control_deduplication=spec["control_deduplication"],
                query_updates=query_updates.marker(),
                retired_both_timeouts=RETIRED_BOTH_TIMEOUTS, reporting_rule=REPORTING_RULE)


def active_members(spec):
    """Resolve pinned predicate updates without changing archived membership."""
    return query_updates.members(spec)


def archived_rows(spec):
    if b.digest(ARCHIVE / "manifest.csv") != spec["input_manifest_sha256"]:
        raise ValueError("Pre-cohort manifest changed")
    rows = b.validate(ARCHIVE)
    pins = {r["query_id"]: r for r in spec["members"]}
    if {r["query_id"] for r in rows} != set(pins) or any(
            identity(row) != identity(pins[row["query_id"]]) for row in rows):
        raise ValueError("Pre-cohort SQL identities changed")
    return rows


def apply(rows, output):
    spec = policy()
    old = archived_rows(spec)
    fields = list(old[0])
    normalized = {r["query_id"]: {k: str(r.get(k, "")) for k in fields} for r in rows}
    # Synthetic graph seeds historically hashed the entire generator. Its
    # pinned successor revision has the same frozen seed definitions and SQL.
    # Preserve predecessor provenance after verifying the emitted SQL below.
    for row in old:
        generated = normalized.get(row["query_id"], {})
        if (generated.get("source_location") == "auto_test/balanced_benchmark.py"
                and generated.get("source_sha256") == b.SYNTHETIC_SOURCE_SHA256):
            generated["source_sha256"] = row["source_sha256"]
    if len(rows) != len(old) or normalized != {r["query_id"]: r for r in old}:
        raise ValueError("Cohort input differs from the frozen predecessor")
    retained_ids = {r["query_id"] for r in spec["members"] if r["role"] != "removed"}
    for row in rows:
        if b.digest(output / row["path"]) != row["content_sha256"]:
            raise ValueError("Changed staged SQL: " + row["path"])
    # Targets are exact manifest paths, already archived and verified above.
    for row in rows:
        if row["query_id"] not in retained_ids:
            (output / row["path"]).unlink()
    retained, sqls, replacements = query_updates.transform(
        [r for r in old if r["query_id"] in retained_ids])
    for previous, current in replacements.items():
        if previous != current:
            (output / previous).unlink()
    for path, sql in sqls.items():
        (output / path).write_text(sql, encoding="utf-8")
    allowed = {r["path"] for r in retained}
    for path in output.glob("*.txt"):
        entries = [replacements.get(line.strip(), line.strip()) for line in path.read_text().splitlines()]
        path.write_text("".join(entry + "\n" for entry in entries if entry in allowed))
    b.write_json(output / MARKER, marker(spec))
    b.write_csv(output / MEMBERSHIP, [r for r in active_members(spec) if r["role"] != "removed"])
    return retained


def validate(corpus):
    spec = policy()
    old = archived_rows(spec)
    original_control_ids = {r["query_id"] for r in spec["members"]
                            if r["role"] == "cost_control" or r["removal_reason"] == DEDUP_REMOVAL_REASON}
    expected_controls = {r["query_id"] for r in deduplicate_tpcds_controls(
        [r for r in old if r["query_id"] in original_control_ids])}
    actual_controls = {r["query_id"] for r in spec["members"] if r["role"] == "cost_control"}
    if len(original_control_ids) != INITIAL_CONTROL_COUNT or actual_controls != expected_controls:
        raise ValueError("TPC-DS source/shape control selection changed")
    retained_ids = {r["query_id"] for r in spec["members"] if r["role"] != "removed"}
    updated, _, _ = query_updates.transform([r for r in old if r["query_id"] in retained_ids])
    expected = {r["query_id"]: r for r in updated}
    rows = b.read_manifest(corpus / "manifest.csv")
    if len(rows) != len(expected) or {r["query_id"]: r for r in rows} != expected:
        raise ValueError("Active cohort membership or metadata changed")
    if json.loads((corpus / MARKER).read_text()) != marker(spec):
        raise ValueError("Cohort marker changed")
    members = [r for r in active_members(spec) if r["role"] != "removed"]
    if b.read_manifest(corpus / MEMBERSHIP) != members:
        raise ValueError("Cohort role mapping changed")
    for source in ARCHIVE.iterdir():
        if (source.is_file() and source.suffix in (".json", ".csv")
                and source.name not in ("manifest.csv", "design_summary.json")):
            target = corpus / source.name
            if not same_dependency(source, target):
                raise ValueError("Historical cohort dependency changed: " + source.name)
    allowed = {r["path"] for r in rows}
    if {str(p.relative_to(corpus)) for p in corpus.glob("*/*.sql")} != allowed:
        raise ValueError("Cohort SQL file set changed")
    for row in rows:
        if b.digest(corpus / row["path"]) != row["content_sha256"]:
            raise ValueError("Cohort SQL changed: " + row["path"])
    for path in corpus.glob("*.txt"):
        if any(line.strip() and line.strip() not in allowed for line in path.read_text().splitlines()):
            raise ValueError("Retired query remains in a query list")
    summary = json.loads((corpus / "design_summary.json").read_text())
    if summary["counts"] != spec["expected_counts_after"] or summary.get("plan_cohort") != marker(spec):
        raise ValueError("Cohort summary changed")
    return rows
