#!/usr/bin/env python3
"""Qualify historically screened candidates using actual target-server evidence.

This is a performance-conditioned subset, not an unbiased overall workload.
Raw input files are never edited. Later observations replace earlier ones,
including failures; eligibility is never inferred from a synthetic speed-up.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import statistics
import subprocess

import balanced_benchmark as benchmark
from benchmark_corpus import read_manifest


def database_signature(path):
    path = path.resolve()
    stat = path.stat()
    payload = json.dumps([str(path), stat.st_size, stat.st_mtime_ns], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def audit_selectivity(root, binary, output, timeout):
    """Read-only base-entity counts, not query timing or cardinality estimates."""
    corpus = root / "benchmark"
    rows = benchmark.validate(corpus)
    design = json.loads(benchmark.DESIGN.read_text())
    used = defaultdict(set)
    for row in rows:
        if benchmark.is_historical_case(row):
            continue
        used[row["selectivity_profile"]].add(row["semantic_tier"])
    measurements = []
    for name, tiers in sorted(used.items()):
        profile = design["profiles"][name]
        family = profile["family"]
        database = Path(os.environ.get(f"{family.upper()}_DB", benchmark.legacy.REPO_ROOT / f"{family}_db"))
        signature = database_signature(database)
        ordered = [tier for tier in benchmark.TIERS if tier in tiers]
        predicates = [benchmark.profile_metadata(design, name, profile["column"], tier)["selectivity_predicate"]
                      for tier in ordered]
        aggregates = ["COUNT(*) AS n"] + [f"COUNT(*) FILTER (WHERE {p}) AS c{i}" for i, p in enumerate(predicates)]
        sql = ("SET disabled_optimizers='outer_yan'; SET threads=4; SELECT " + ", ".join(aggregates)
               + " FROM " + profile["calibration_from"] + ";")
        result = subprocess.run([str(binary), "-readonly", "-no-init", "-bail", "-json", str(database), "-c", sql],
                                capture_output=True, text=True, check=True, timeout=timeout)
        if database_signature(database) != signature:
            raise ValueError(f"Database changed during audit: {database}")
        counts = json.loads(result.stdout)[0]
        for i, tier in enumerate(ordered):
            fraction = counts[f"c{i}"] / counts["n"] if counts["n"] else 0
            band = design["tiers"][benchmark.TIERS.index(tier)]
            measurements.append(dict(profile=name, family=family, tier=tier, database=str(database.resolve()),
                                     database_signature=signature, predicate=predicates[i], total_rows=counts["n"],
                                     qualified_rows=counts[f"c{i}"], observed_fraction=fraction,
                                     in_range=benchmark.legacy.fraction_in_band(fraction, band)))
        print(f"Audited {name}: " + ", ".join(f"{m['tier']}={m['observed_fraction']:.4%}"
              for m in measurements if m["profile"] == name), flush=True)
    success = all(m["in_range"] for m in measurements)
    benchmark.write_json(output, dict(revision=benchmark.REVISION, execution_host=socket.gethostname(),
                         manifest_sha256=benchmark.digest(corpus / "manifest.csv"),
                         design_sha256=benchmark.digest(benchmark.DESIGN), profiles=measurements,
                         all_used_bands_in_range=success,
                         historical_cases_outside_band_audit=[r["query_id"] for r in rows
                                                             if benchmark.is_historical_case(r)],
                         scope="Base-entity cohorts including NULL rows in denominator, not join-output selectivity"))
    print(f"Selectivity audit: {'PASS' if success else 'OUT OF BAND'}; {output}")
    return success


def classify(candidate, result, audit, manifest_hash, expected_host="cpu9"):
    """Return one auditable exclusion reason; fail closed on missing provenance."""
    if benchmark.is_historical_case(candidate):
        # These exact legacy definitions are not part of the three-band design.
        # Preserve every observed result separately, without claiming qualification.
        return "historical_case_reported_separately"
    if result is None:
        return "pending_measurement"
    if not audit:
        return "selectivity_audit_missing"
    if result.get("corpus_revision") != benchmark.REVISION or result.get("sql_content_sha256") != candidate["content_sha256"]:
        return "sql_or_revision_mismatch"
    if result.get("corpus_manifest_sha256") != manifest_hash:
        return "manifest_mismatch"
    host = result.get("execution_host", "")
    if host.split(".")[0] != expected_host or host != audit.get("execution_host"):
        return "host_mismatch"
    if audit.get("manifest_sha256") != manifest_hash or audit.get("design_sha256") != benchmark.digest(benchmark.DESIGN):
        return "audit_revision_mismatch"
    profiles = [p for p in audit.get("profiles", []) if p["profile"] == candidate["selectivity_profile"]
                and p["tier"] == candidate["semantic_tier"]]
    if len(profiles) != 1 or not profiles[0]["in_range"]:
        return "selectivity_unverified_or_out_of_band"
    if result.get("database_signature") != profiles[0]["database_signature"]:
        return "database_mismatch"
    timeout = benchmark.QUALIFICATION_TIMEOUT_SECONDS
    limits = [result.get(f"{side}_timeout_seconds", result.get("timeout_seconds"))
              for side in ("duckdb", "outeryan")]
    if any(limit != str(timeout) for limit in limits):
        return f"requires_{timeout}s_run"
    if "TIMEOUT" in result.get("note", "").upper() or "timeout" in result.get("timing_status", "").lower():
        return f"timeout_at_{timeout}s"
    if result.get("timing_status", "").lower() == "fallback-skip":
        return "fallback_not_measured"
    unchecked = (result.get("correct", "").upper() == "NOT-CHECKED"
                 and result.get("correctness_check") == "disabled")
    if result.get("correct", "").upper() != "TRUE" and not unchecked:
        return "correctness_not_verified"
    if result.get("timing_status", "").lower() != "measured":
        return "timing_not_measured"
    try:
        off, on = float(result["tm_off"]), float(result["tm_on"])
    except (ValueError, KeyError):
        return "invalid_timing"
    if not all(math.isfinite(t) and t > 0 for t in (off, on)):
        return "invalid_timing"
    if max(off, on) >= timeout:
        return "runtime_at_or_above_timeout"
    if min(off, on) <= 1:
        return "runtime_not_above_1s"
    if off / on < .8:
        return "speedup_below_0.8"
    return "eligible"


def speed_statistics(rows):
    values = [float(r["tm_off"]) / float(r["tm_on"]) for r in rows]
    return dict(n=len(values), geomean=math.exp(statistics.mean(map(math.log, values))) if values else None,
                min=min(values) if values else None, max=max(values) if values else None,
                median=statistics.median(values) if values else None,
                std=statistics.stdev(values) if len(values)>1 else None)


def qualify(corpora, audits, results, output, target=180, host="cpu9"):
    if target <= 0 or target % 3:
        raise ValueError("target-per-family must be positive and divisible by three")
    if audits and len(corpora) != len(audits):
        raise ValueError("Provide one --selectivity-audit per --corpus, in matching order")
    candidates, metadata = {}, {}
    for index, corpus in enumerate(corpora):
        manifest_hash = benchmark.digest(corpus / "manifest.csv")
        audit = json.loads(audits[index].read_text()) if audits else {}
        for row in benchmark.validate(corpus):
            key = (row["family"], row["query_id"])
            if key in candidates:
                raise ValueError(f"Duplicate candidate in corpus inputs: {key}")
            candidates[key] = row
            metadata[key] = (audit, manifest_hash, str(corpus))
    observed, sources, configurations = {}, [], set()
    for path in results:
        for row in read_manifest(path):
            key = (row.get("family"), row.get("query"))
            if key not in candidates:
                raise ValueError(f"Result not in input candidate corpus: {path}: {key}")
            configurations.add((row.get("execution_host"), row.get("timing_threads"), row.get("formula_id")))
            observed[key] = dict(row, qualification_source_csv=str(path))
        sources.append(dict(path=str(path), sha256=benchmark.digest(path)))
    # Different threads/hosts must not silently become one benchmark population.
    host_threads = {(h, t) for h, t, _ in configurations}
    if len(host_threads) > 1:
        raise ValueError("Mixed hosts or timing thread counts; qualify each configuration separately")
    formulas = {f for _, _, f in configurations if f not in (None, "-", "NA", "")}
    if len(formulas) > 1:
        raise ValueError("Mixed cost-model revisions; qualify separately")
    protocols = {(r.get("timing_protocol", "legacy"), r.get("timing_samples", "legacy"),
                  r.get("timing_estimator", "legacy"), r.get("correctness_check", "legacy"))
                 for r in observed.values()}
    if len(protocols) > 1:
        raise ValueError("Mixed timing/correctness protocols; qualify each protocol separately")
    for family in benchmark.FAMILIES:
        signatures = {r.get("database_signature") for r in observed.values() if r.get("family") == family}
        if len(signatures) > 1:
            raise ValueError(f"Mixed database signatures for {family}; do not combine different data snapshots")
    detail, eligible = [], defaultdict(list)
    for key, candidate in candidates.items():
        audit, manifest_hash, corpus = metadata[key]
        result = observed.get(key)
        reason = classify(candidate, result, audit, manifest_hash, host)
        row = dict(candidate, qualification_reason=reason, qualification_corpus=corpus,
                   qualification_source_csv=result.get("qualification_source_csv", "") if result else "",
                   tm_off=result.get("tm_off", "") if result else "", tm_on=result.get("tm_on", "") if result else "")
        detail.append(row)
        if reason == "eligible":
            eligible[(candidate["family"], candidate["semantic_tier"])].append(row)
    selected, counts = [], []
    for family in benchmark.FAMILIES:
        for tier in benchmark.TIERS:
            pool = eligible[(family, tier)]
            # Balance retained shapes where possible; never rank by achieved speed.
            used = Counter()
            chosen = []
            while pool and len(chosen) < target // 3:
                row = min(pool, key=lambda r: (used[r["tree_shape"]], r["query_id"]))
                pool.remove(row)
                used[row["tree_shape"]] += 1
                chosen.append(row)
            selected.extend(chosen)
            counts.append(dict(family=family, tier=tier, target=target//3, eligible=len(chosen)+len(pool),
                               selected=len(chosen), shortage=target//3-len(chosen)))
    retained = {(r["family"], r["query_id"]) for r in selected}
    for row in detail:
        row["included"] = (row["family"], row["query_id"]) in retained
    output.mkdir(parents=True, exist_ok=True)
    benchmark.write_csv(output / "qualification.csv", detail)
    benchmark.write_csv(output / "coverage.csv", counts)
    benchmark.write_csv(output / "qualified_manifest.csv", selected, list(detail[0]))
    qualified_results = []
    for row in selected:
        result = dict(observed[(row["family"], row["query_id"])] ,
                      qualification_policy="performance_screened", tree_shape=row["tree_shape"].replace("_", "-"),
                      join_graph_topology=row["topology"], join_vector=row["join_vector"],
                      selectivity_tier=row["selectivity_tier"], selectivity_profile=row["selectivity_profile"],
                      source_component=row["source_component"], evaluation_role=row["evaluation_role"])
        qualified_results.append(result)
    fields = list(dict.fromkeys(k for row in observed.values() for k in row)) or ["query", "family", "tm_off", "tm_on"]
    fields += [k for row in qualified_results for k in row if k not in fields]
    fields = list(dict.fromkeys(fields))
    benchmark.write_csv(output / "qualified_results.csv", qualified_results, fields)
    supplementary_results = []
    for key, candidate in candidates.items():
        if benchmark.is_historical_case(candidate) and key in observed:
            supplementary_results.append(dict(
                observed[key], qualification_policy="historical_case_unqualified_raw_result",
                evaluation_role=candidate["evaluation_role"], source_component=candidate["source_component"],
                selectivity_tier=candidate["selectivity_tier"], selectivity_profile=candidate["selectivity_profile"]))
    supplementary_fields = list(dict.fromkeys(fields + [k for r in supplementary_results for k in r]))
    benchmark.write_csv(output / "supplementary_results.csv", supplementary_results, supplementary_fields)
    lists = []
    for index, corpus in enumerate(corpora):
        name = "qualified_query_paths.txt" if len(corpora) == 1 else f"qualified_query_paths_batch{index}.txt"
        (output / name).write_text("".join(r["path"] + "\n" for r in selected if r["qualification_corpus"] == str(corpus)))
        lists.append(dict(corpus=str(corpus.resolve()), query_list=name,
                          manifest_sha256=benchmark.digest(corpus / "manifest.csv"),
                          audit_sha256=benchmark.digest(audits[index]) if audits else None))
    benchmark.write_json(output / "qualification_inputs.json", lists)
    summary = dict(status="COMPLETE" if all(c["shortage"]==0 for c in counts) else "INCOMPLETE",
                   policy="Historically/performance-screened subset, not unbiased overall performance; "
                          f"eligible measured pairs only, both runtimes >1s and <{benchmark.QUALIFICATION_TIMEOUT_SECONDS}s, speedup >=0.8; "
                          "explicit NOT-CHECKED/disabled rows are performance-only, not correctness-verified; "
                          "latest supplied observations win, including failures; no fallback imputation",
                   target_host=host, target_per_family=target, candidates=len(detail), selected=len(selected),
                   qualification_timeout_seconds=benchmark.QUALIFICATION_TIMEOUT_SECONDS,
                   unchecked_selected=sum(r.get("correct") == "NOT-CHECKED" for r in qualified_results),
                   balanced_candidates=sum(not benchmark.is_historical_case(r) for r in detail),
                   historical_supplementary_candidates=sum(benchmark.is_historical_case(r) for r in detail),
                   historical_supplementary_observations=len(supplementary_results),
                   reasons=dict(Counter(r["qualification_reason"] for r in detail)), coverage=counts, sources=sources,
                   statistics={f:speed_statistics([r for r in selected if r["family"]==f]) for f in benchmark.FAMILIES},
                   outeryan_selected_statistics={f:speed_statistics([r for r in qualified_results
                       if r["family"]==f and r.get("selected_plan", "").upper()=="OUTERYAN"]) for f in benchmark.FAMILIES})
    benchmark.write_json(output / "qualification_summary.json", summary)
    print(f"{summary['status']}: {len(selected)}/{4*target} qualified; details: {output}")
    for family in benchmark.FAMILIES:
        group = [c for c in counts if c["family"] == family]
        print(f"  {family}: {sum(c['selected'] for c in group)}/{target}; "
              + ", ".join(f"{c['tier']} short {c['shortage']}" for c in group))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, action="append", help="Repeat for disjoint batches; default current benchmark")
    parser.add_argument("--selectivity-audit", type=Path, action="append", help="One audit per corpus, in matching order")
    parser.add_argument("--results", type=Path, nargs="*", default=[], help="CSV files oldest to newest; later rows win")
    parser.add_argument("--target-per-family", type=int, default=180)
    parser.add_argument("--host", default="cpu9")
    parser.add_argument("--output-dir", type=Path, default=benchmark.legacy.SCRIPT_DIR / "results/qualification")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    report = qualify(args.corpus or [benchmark.ROOT / "benchmark"], args.selectivity_audit or [], args.results,
                     args.output_dir, args.target_per_family, args.host)
    if args.require_complete and report["status"] != "COMPLETE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
