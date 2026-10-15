#!/usr/bin/env python3
"""Report frozen cohort observations with explicit fallback and timeout policies.

Raw CSVs are read-only. Effective times live in separate fields and must not be
passed off as measurements. A warmup timeout is not a steady-state speedup bound.
"""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import statistics

import balanced_benchmark as b
import benchmark_plan_cohort as cohort

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "auto_test/results/plots/20261014"
LABELS = {"graph": "SGPB", "tpch": "TPC-H", "tpcds": "TPC-DS", "job": "JOB"}


def positive(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def observation(member, raw):
    """Retain original values and derive the user-requested reporting values."""
    expected_hash = member.get("measurement_content_sha256") or member["content_sha256"]
    if raw.get("sql_content_sha256") != expected_hash:
        raise ValueError("SQL hash mismatch: " + member["query_id"])
    row = dict(query=member["query_id"], family=member["family"], role=member["role"],
               source_csv=member["decision_source"], source_query=member["decision_query"],
               sql_content_sha256=member["content_sha256"],
               source_sql_content_sha256=raw["sql_content_sha256"],
               selected_plan=raw.get("selected_plan", ""),
               recorded_timing_status=raw.get("timing_status", ""),
               recorded_duckdb_s=raw.get("tm_off", ""), recorded_outeryan_s=raw.get("tm_on", ""),
               duckdb_status=raw.get("duckdb_status", ""), outeryan_status=raw.get("outeryan_status", ""),
               duckdb_timeout_stage=raw.get("duckdb_timeout_stage", ""),
               outeryan_timeout_stage=raw.get("outeryan_timeout_stage", ""),
               effective_duckdb_s=None, effective_outeryan_s=None, speedup=None,
               speedup_source="excluded", exclusion_reason="missing_or_invalid_measurement")
    if raw.get("correct", "").upper() in ("FALSE", "ERROR", "NOT-EQUIV"):
        row["exclusion_reason"] = "correctness_failure"
        return row
    off_status, on_status = row["duckdb_status"], row["outeryan_status"]
    if on_status == "timeout":
        row["exclusion_reason"] = "both_engines_timeout" if off_status == "timeout" else "outeryan_timeout"
        return row
    if (row["selected_plan"] == "DUCKDB"
            and raw.get("timing_status") == "fallback-skip"
            and off_status == on_status == "fallback-skip"):
        row.update(speedup=1.0, speedup_source="fallback_default_1x", exclusion_reason="")
        return row
    off, on = positive(raw.get("tm_off")), positive(raw.get("tm_on"))
    if row["selected_plan"] != "OUTERYAN":
        return row
    if (off_status == "timeout" and on_status == "measured" and on is not None
            and positive(raw.get("duckdb_timeout_seconds")) == 600):
        row.update(effective_duckdb_s=600.0, effective_outeryan_s=on,
                   speedup=600.0 / on, speedup_source="duckdb_timeout_600s", exclusion_reason="")
    elif (off_status == on_status == "measured" and raw.get("timing_status") == "measured"
          and off is not None and on is not None):
        row.update(effective_duckdb_s=off, effective_outeryan_s=on,
                   speedup=off / on, speedup_source="measured", exclusion_reason="")
    return row


def summarize(rows, family, scope):
    rows = [r for r in rows if (family == "All" or r["family"] == family)
            and (scope == "all_queries" or r["selected_plan"] == "OUTERYAN")]
    valid = [r for r in rows if r["speedup"] is not None]
    ratios = [r["speedup"] for r in valid]
    measured = [r for r in valid if r["speedup_source"] == "measured"]
    pairs = [r for r in valid if r["effective_duckdb_s"] is not None]
    states = Counter(r["speedup_source"] for r in valid)
    off = math.fsum(r["effective_duckdb_s"] for r in pairs)
    on = math.fsum(r["effective_outeryan_s"] for r in pairs)
    raw_off = math.fsum(r["effective_duckdb_s"] for r in measured)
    raw_on = math.fsum(r["effective_outeryan_s"] for r in measured)
    return dict(scope=scope, family=LABELS.get(family, family), input_n=len(rows), n=len(valid),
                measured_n=len(measured), capped_n=states["duckdb_timeout_600s"],
                fallback_n=states["fallback_default_1x"], excluded_n=len(rows) - len(valid),
                geomean=math.exp(math.fsum(map(math.log, ratios)) / len(ratios)) if ratios else None,
                median=statistics.median(ratios) if ratios else None,
                min=min(ratios) if ratios else None, max=max(ratios) if ratios else None,
                std_population=statistics.pstdev(ratios) if ratios else None,
                faster=sum(r > 1 for r in ratios), equal=sum(r == 1 for r in ratios),
                slower=sum(r < 1 for r in ratios), effective_pair_n=len(pairs),
                effective_duckdb_sum_s=off, effective_outeryan_sum_s=on,
                effective_total_ratio=off / on if on else None,
                measured_duckdb_sum_s=raw_off, measured_outeryan_sum_s=raw_on,
                measured_total_ratio=raw_off / raw_on if raw_on else None,
                measured_max=max((r["speedup"] for r in measured), default=None))


def load_observations(csv_paths=None):
    """Read pinned historical inputs, or one complete new run, never mix them."""
    spec = cohort.policy()
    active = {r["query_id"]: r for r in b.validate(b.ROOT / "benchmark")}
    sources = {}
    source_files = spec["source_files"] + cohort.query_updates.source_files() if not csv_paths else [
        dict(path=str(Path(p).resolve()), sha256=b.digest(Path(p))) for p in csv_paths]
    fresh = {}
    for source in source_files:
        path = ROOT / source["path"]
        if b.digest(path) != source["sha256"]:
            raise ValueError("Pinned measurement file changed: " + str(path))
        with path.open(newline="") as handle:
            records = list(csv.DictReader(handle))
        sources[source["path"]] = {r["query"]: r for r in records}
        if len(sources[source["path"]]) != len(records):
            raise ValueError("Ambiguous duplicate measurement IDs")
        if csv_paths:
            for record in records:
                if record["query"] in fresh:
                    raise ValueError("Duplicate query across input CSVs: " + record["query"])
                fresh[record["query"]] = (source["path"], record)
    if csv_paths and set(fresh) != set(active):
        raise ValueError(f"New run must cover exactly the active {len(active)} queries: "
                         f"missing={len(set(active) - set(fresh))}, extra={len(set(fresh) - set(active))}")
    if csv_paths:
        for key in ("timing_threads", "timing_samples", "timing_protocol", "duckdb_timeout_seconds", "outeryan_timeout_seconds"):
            values = {r.get(key) for _, r in fresh.values() if r.get(key)}
            if len(values) > 1:
                raise ValueError("New-run CSVs have incompatible settings for " + key)
    details, retired, observations = [], [], []
    for member in cohort.active_members(spec):
        if member["role"] == "removed" and member["removal_reason"] != "both_engines_timeout":
            continue
        if csv_paths:
            if member["role"] == "removed":
                continue
            path, raw = fresh[member["query_id"]]
            member = dict(member, decision_source=path, decision_query=raw["query"],
                          measurement_content_sha256="")
        else:
            raw = sources[member["decision_source"]][member["decision_query"]]
        row = observation(member, raw)
        if member["role"] == "removed":
            if row["exclusion_reason"] != "both_engines_timeout":
                raise ValueError("Retirement does not match both-engine timeout evidence")
            retired.append(row)
        else:
            if member["query_id"] not in active:
                raise ValueError("Report references an inactive query")
            details.append(row)
            observations.append(dict(raw, query=member["query_id"], source_query=raw["query"],
                                     source_csv=member["decision_source"],
                                     sql_content_sha256=member["content_sha256"],
                                     source_sql_content_sha256=raw["sql_content_sha256"]))
    return details, retired, observations, source_files


def build(csv_paths=None):
    spec = cohort.policy()
    details, retired, _, source_files = load_observations(csv_paths)
    stats = [summarize(details, family, scope)
             for scope in ("all_queries", "outeryan_selected")
             for family in ("graph", "tpch", "tpcds", "job", "All")]
    return details, retired, stats, dict(
        reporting_rule=spec["reporting_rule"], benchmark_queries=len(details),
        retired_both_timeout_queries=len(retired),
        active_manifest_sha256=b.digest(b.ROOT / "benchmark/manifest.csv"),
        policy_sha256=b.digest(cohort.POLICY), query_updates=cohort.query_updates.marker(), sources=source_files,
        measurement_mode="new_run" if csv_paths else "pinned_historical_observations",
        total_definition="Effective sums cover measured and capped pairs only, never fallback placeholders.",
        timeout_interpretation="600 s is an assigned timeout-limit proxy. A warmup timeout does not prove "
                               "a post-warmup runtime lower bound. Original statuses and times are unchanged.",
        statistics=stats)


def write_outputs(out, csv_paths=None):
    details, retired, stats, summary = build(csv_paths)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("results", details), ("retired_both_timeouts", retired), ("statistics", stats)):
        if rows:
            b.write_csv(out / ("plan_cohort_" + name + ".csv"), rows)
        else:
            with (out / ("plan_cohort_" + name + ".csv")).open("w", newline="") as handle:
                csv.writer(handle).writerow(list(details[0]))
    b.write_json(out / "plan_cohort_summary.json", summary)
    return details, stats, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--csv", type=Path, action="append", help="Explicit complete new-run CSV; no historical mixing")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    _, stats, _ = write_outputs(out, args.csv)
    display = lambda value: "NA" if value is None else f"{value:.6f}"
    for row in stats:
        print(f"{row['scope']:18s} {row['family']:7s} n={row['n']:3d} "
              f"geomean={display(row['geomean'])} median={display(row['median'])} max={display(row['max'])}")
    print("Outputs:", out)


if __name__ == "__main__":
    main()
