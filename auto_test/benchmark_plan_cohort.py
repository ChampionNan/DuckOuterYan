"""Frozen plan-selection cohort; keep SQL recoverable and generation result-free.

Only --freeze reads measurements. Normal generation applies pinned membership,
never promotes an unmeasured candidate or treats a fallback's 1x as a timing.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

import balanced_benchmark as b
from workload_policy import validate_pins


REVISION = "selected-plus-cost-controls-20261014"
POLICY = b.ROOT / "sources/plan_cohort_20261014.json"
ARCHIVE = b.ROOT / "revisions/pre_plan_cohort_20261014/benchmark"
MARKER = "plan_cohort.json"
MEMBERSHIP = "plan_cohort.csv"
PIN_FIELDS = ("query_id", "family", "path", "content_sha256", "sql_fingerprint")
CONTROL_COUNT = 65
RETIRED_BOTH_TIMEOUTS = 21
REPORTING_RULE = dict(fallback_speedup=1.0, duckdb_only_timeout_seconds=600,
                      outeryan_timeout="exclude", both_timeout="remove_from_benchmark",
                      raw_measurements="preserve", capped_speedup="timeout_limit_proxy_not_measured")


def policy():
    spec = json.loads(POLICY.read_text())
    validate_pins(spec, "members")
    if len(spec["members"]) != 720 or len({r["query_id"] for r in spec["members"]}) != 720:
        raise ValueError("Expected the complete 720-query source cohort")
    roles = Counter(r["role"] for r in spec["members"])
    if roles != {"selected": 285, "cost_control": CONTROL_COUNT, "removed": 370}:
        raise ValueError("Cohort role counts changed")
    if sum(r["role"] != "removed" for r in spec["members"]) != 350:
        raise ValueError("Cohort membership changed")
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
    # The earlier screen also records the synthetic generator's whole-file hash.
    old, new = b.read_manifest(source), b.read_manifest(target)
    if len(old) != len(new):
        return False
    for expected, generated in zip(old, new):
        if (generated.get("source_location") == "auto_test/balanced_benchmark.py"
                and generated.get("source_sha256") == b.digest(Path(b.__file__))):
            generated["source_sha256"] = expected["source_sha256"]
    return old == new


def choose_controls(rows, decisions, count=CONTROL_COUNT):
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


def freeze(source_csv, extra_csvs=()):
    """One-time explicit import. Source hashes retained, runtime values excluded."""
    if POLICY.exists() or ARCHIVE.exists():
        raise ValueError("Frozen cohort already exists; refusing to overwrite")
    corpus = b.ROOT / "benchmark"
    rows = b.validate(corpus)
    if len(rows) != 720:
        raise ValueError("Expected the current full 720-query benchmark")
    references = b.read_manifest(source_csv)
    by_id = {r["query"]: r for r in references}
    if len(by_id) != len(references) or set(by_id) != {r["query_id"] for r in rows}:
        raise ValueError("Reference must cover exactly the active query identities")
    extra_by_sha = {}
    for path in extra_csvs:
        for row in b.read_manifest(path):
            if row.get("sql_content_sha256"):
                extra_by_sha.setdefault(row["sql_content_sha256"], []).append((path, row))
    decisions, evidence = {}, []
    for row in rows:
        reference = by_id[row["query_id"]]
        source, reference_id = source_csv, reference["query"]
        if reference.get("sql_content_sha256") != row["content_sha256"]:
            matches = extra_by_sha.get(row["content_sha256"], [])
            if len(matches) != 1:
                raise ValueError("Missing exact-SQL decision for " + row["query_id"])
            source, reference = matches[0]
            reference_id = reference["query"]
        if reference["selected_plan"] not in ("DUCKDB", "OUTERYAN"):
            raise ValueError("Unknown selection: " + row["query_id"])
        decisions[row["query_id"]] = reference
        evidence.append(dict(query_id=row["query_id"], decision_source=str(source.relative_to(b.legacy.REPO_ROOT)),
                             decision_query=reference_id))
    selected = {q for q, r in decisions.items() if r["selected_plan"] == "OUTERYAN"}
    if len(selected) != 306:
        raise ValueError("Expected all 306 selected queries, including timeouts")
    controls = {r["query_id"] for r in choose_controls(rows, decisions)}
    retired = {q for q in selected if decisions[q].get("duckdb_status") == "timeout"
               and decisions[q].get("outeryan_status") == "timeout"}
    if len(retired) != RETIRED_BOTH_TIMEOUTS:
        raise ValueError("Expected 21 selected queries with both engines timed out")
    selected -= retired
    members = []
    for row, ref in zip(rows, evidence):
        q = row["query_id"]
        reason = decisions[q]["decision_reason"]
        role = "selected" if q in selected else "cost_control" if q in controls else "removed"
        removal = ""
        if role == "removed":
            removal = ("both_engines_timeout" if q in retired else
                       "three_relation_fallback" if int(row["relation_count"]) == 3 else
                       "same_grouping" if reason == "DUCKDB_PLAN" else
                       "inapplicable" if reason == "INAPPLICABLE" else
                       "uncertainty_guard" if reason == "COST_UNCERTAIN_FILTER_AMPLIFICATION" else
                       "cost_control_quota")
        members.append(dict(identity(row), role=role, reference_selected_plan=decisions[q]["selected_plan"],
                            reference_decision_reason=reason, removal_reason=removal, **{
                                k: v for k, v in ref.items() if k != "query_id"}))
    spec = dict(revision=REVISION, representation="frozen_workload_definition",
                archive="revisions/pre_plan_cohort_20261014/benchmark",
                input_manifest_sha256=b.digest(corpus / "manifest.csv"),
                source_files=[dict(path=str(p.relative_to(b.legacy.REPO_ROOT)), sha256=b.digest(p))
                              for p in (source_csv, *extra_csvs)],
                reporting_rule=REPORTING_RULE,
                selection="Start with all 306 historically selected plans, then retire the 21 with both engines timed out. "
                          "Keep 285 selected plans, including six three-table queries and four DuckDB-only timeouts. "
                          "Keep 65 COST_DUCKDB_BETTER controls with at least four relations. "
                          "Preserve the controls chosen before timeout retirement by family, tier, shape, source, size and query type. "
                          "Do not use measured speedup or runtime to select these controls. "
                          "Other fallbacks, including uncertainty guards, are archived. "
                          "This is plan-selection-conditioned curation, not an unbiased workload sample.",
                expected_counts_before=dict(Counter(r["family"] for r in rows)),
                expected_counts_after=dict(Counter(r["family"] for r in members if r["role"] != "removed")),
                control_counts=dict(Counter(r["family"] for r in members if r["role"] == "cost_control")),
                members=members)
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(corpus, ARCHIVE)
    if b.digest(ARCHIVE / "manifest.csv") != spec["input_manifest_sha256"]:
        raise ValueError("Archive copy changed")
    b.write_json(POLICY, spec)
    policy()
    print("Frozen membership:", spec["expected_counts_after"], "controls:", spec["control_counts"])


def marker(spec):
    return dict(revision=spec["revision"], policy_sha256=b.digest(POLICY),
                counts=spec["expected_counts_after"], selected=285, cost_controls=65, removed=370,
                retired_both_timeouts=RETIRED_BOTH_TIMEOUTS, reporting_rule=REPORTING_RULE)


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
    # Synthetic graph seeds historically hashed the entire generator. Adding
    # this membership stage changes that file, not the frozen seed or its SQL.
    # Preserve predecessor provenance after verifying the emitted SQL below.
    for row in old:
        generated = normalized.get(row["query_id"], {})
        if (generated.get("source_location") == "auto_test/balanced_benchmark.py"
                and generated.get("source_sha256") == b.digest(Path(b.__file__))):
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
    retained = [r for r in old if r["query_id"] in retained_ids]
    allowed = {r["path"] for r in retained}
    for path in output.glob("*.txt"):
        path.write_text("".join(line for line in path.read_text().splitlines(keepends=True)
                                if line.strip() in allowed))
    b.write_json(output / MARKER, marker(spec))
    b.write_csv(output / MEMBERSHIP, [r for r in spec["members"] if r["role"] != "removed"])
    return retained


def validate(corpus):
    spec = policy()
    old = archived_rows(spec)
    retained_ids = {r["query_id"] for r in spec["members"] if r["role"] != "removed"}
    expected = {r["query_id"]: r for r in old if r["query_id"] in retained_ids}
    rows = b.read_manifest(corpus / "manifest.csv")
    if len(rows) != len(expected) or {r["query_id"]: r for r in rows} != expected:
        raise ValueError("Active cohort membership or metadata changed")
    if json.loads((corpus / MARKER).read_text()) != marker(spec):
        raise ValueError("Cohort marker changed")
    members = [r for r in spec["members"] if r["role"] != "removed"]
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, help="Explicit historical CSV import, once only")
    parser.add_argument("--extra-results", type=Path, action="append", default=[])
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        freeze(args.freeze.resolve(), tuple(p.resolve() for p in args.extra_results))
    if args.promote:
        b.generate()
    if not args.freeze and not args.promote:
        print("Validated", len(validate(b.ROOT / "benchmark")), "active queries")
