#!/usr/bin/env python3
"""Descriptive ON/OFF statistics for a deduplicated, single-thread-setting run.

Keep failed and incomplete queries for coverage accounting. Timing statistics
use only correct queries with finite positive OFF/ON pairs. No censoring-value
imputation, speed-up-based trimming, or representative-query sampling is used.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def distribution(values: pd.Series) -> dict:
    """Sample SD/variance; linear-interpolated percentiles; no empty-set zeros."""
    if values.empty:
        return dict.fromkeys(("min", "max", "mean", "geomean", "median", "stddev", "variance",
                              "cv", "p05", "p10", "p25", "p75", "p90", "p95", "p99"))
    mean = float(values.mean())
    sd = float(values.std(ddof=1)) if len(values) > 1 else None
    result = {
        "min": float(values.min()), "max": float(values.max()), "mean": mean,
        "geomean": float(np.exp(np.log(values).mean())), "median": float(values.median()),
        "stddev": sd, "variance": float(values.var(ddof=1)) if len(values) > 1 else None,
        "cv": sd / mean if sd is not None else None,
    }
    result.update({f"p{percent:02d}": float(values.quantile(percent / 100, interpolation="linear"))
                   for percent in (5, 10, 25, 75, 90, 95, 99)})
    return result


def prepare_queries(frame: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Normalize reported outcomes without requiring the rounded speedup field."""
    if metric not in ("tm", "t1"):
        raise ValueError("metric must be tm or t1")
    if "run" in frame and frame["run"].nunique() > 1:
        raise ValueError("statistics require one logical run; do not mix thread configurations")
    if "timing_threads" in frame and frame["timing_threads"].nunique() > 1:
        raise ValueError("statistics require one timing thread count")
    if frame.duplicated(["family", "query"]).any():
        raise ValueError("deduplicate final and attempts rows before computing statistics")
    columns = [column for column in ("query", "family", "topology", "selected_plan", "correct", "note",
                                      "timing_threads", "sql_path") if column in frame]
    detail = frame[columns].copy().reset_index(drop=True)
    detail["selected_plan"] = detail.get("selected_plan", pd.Series("UNKNOWN", index=detail.index)).fillna(
        "UNKNOWN").astype(str).str.upper()
    correct = detail.get("correct", pd.Series("TRUE", index=detail.index)).astype(str).str.upper().eq("TRUE")
    notes = detail.get("note", pd.Series("", index=detail.index)).fillna("").astype(str)
    missing = pd.Series(np.nan, index=frame.index)
    off = pd.to_numeric(frame.get(f"{metric}_off", missing), errors="coerce").reset_index(drop=True)
    on = pd.to_numeric(frame.get(f"{metric}_on", missing), errors="coerce").reset_index(drop=True)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore", under="ignore"):
        speedup = off / on
    pair = np.isfinite(off) & off.gt(0) & np.isfinite(on) & on.gt(0)
    timeout = notes.str.contains("TIMEOUT", case=False, regex=False)
    valid = correct & ~timeout & pair & np.isfinite(speedup) & speedup.gt(0)
    detail["off_s"], detail["on_s"] = off, on
    detail["speedup"] = speedup.where(valid)
    detail["valid_timing"] = valid
    # Exclusive reasons make coverage totals reconcile without double-counting.
    detail["exclusion_reason"] = np.select(
        [valid, timeout, ~correct, ~pair],
        ["", "timeout", "correctness_not_true", "missing_or_invalid_timing"],
        default="nonfinite_or_nonpositive_ratio",
    )
    return detail


def summarize(rows: pd.DataFrame) -> dict:
    valid = rows.loc[rows["valid_timing"]]
    speedup = valid["speedup"]
    counts = {
        "total": len(rows), "valid": len(valid), "excluded": len(rows) - len(valid),
        "timeouts": int(rows["exclusion_reason"].eq("timeout").sum()),
        "correctness_not_true": int(rows["exclusion_reason"].eq("correctness_not_true").sum()),
        "missing_or_invalid_timing": int(rows["exclusion_reason"].eq("missing_or_invalid_timing").sum()),
        "nonfinite_or_nonpositive_ratio": int(rows["exclusion_reason"].eq("nonfinite_or_nonpositive_ratio").sum()),
        "faster": int(speedup.gt(1).sum()), "equal": int(speedup.eq(1).sum()), "slower": int(speedup.lt(1).sum()),
        "speedup_gt_1_05": int(speedup.gt(1.05).sum()),
        "speedup_in_0_95_to_1_05": int(speedup.between(0.95, 1.05).sum()),
        "speedup_lt_0_95": int(speedup.lt(0.95).sum()),
        "speedup_ge_2": int(speedup.ge(2).sum()), "speedup_ge_10": int(speedup.ge(10).sum()),
    }
    total_off = float(valid["off_s"].sum()) if len(valid) else None
    total_on = float(valid["on_s"].sum()) if len(valid) else None
    stats = distribution(speedup)
    for name in ("min", "max"):
        stats[f"{name}_queries"] = sorted(valid.loc[speedup.eq(stats[name]), "query"].tolist())
    return {
        "counts": counts, "speedup": stats,
        "off_s": distribution(valid["off_s"]), "on_s": distribution(valid["on_s"]),
        "totals": {"off_s": total_off, "on_s": total_on,
                   "speedup": total_off / total_on if total_on is not None else None,
                   "saved_s": total_off - total_on if total_on is not None else None,
                   "time_reduction_fraction": 1 - total_on / total_off if total_off is not None else None},
    }


def build_statistics(frame: pd.DataFrame, metric: str = "tm", sources: list[str] | None = None) -> dict:
    detail = prepare_queries(frame, metric)
    groups = []
    for subset, rows in (("all", detail),
                         ("outeryan_selected", detail.loc[detail["selected_plan"].eq("OUTERYAN")]),
                         ("duckdb_selected", detail.loc[detail["selected_plan"].eq("DUCKDB")])):
        groups.append({"subset": subset, "scope": "overall", "family": "all", "topology": "all",
                       **summarize(rows)})
        for scope, keys in (("benchmark", ["family"]), ("shape", ["topology"]),
                            ("benchmark_shape", ["family", "topology"])):
            for group_keys, group_rows in rows.groupby(keys, sort=True):
                if not isinstance(group_keys, tuple):
                    group_keys = (group_keys,)
                identity = dict(zip(keys, group_keys))
                groups.append({"subset": subset, "scope": scope, "family": identity.get("family", "all"),
                               "topology": identity.get("topology", "all"), **summarize(group_rows)})
    source_info = []
    for source in sources or []:
        path = Path(source).resolve()
        source_info.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "rows": len(pd.read_csv(path)),
                            "kind": "attempts" if path.name.endswith(".attempts.csv") else "final"})
    return {
        "schema_version": 1, "run": str(frame["run"].iloc[0]) if "run" in frame and len(frame) else None,
        "metric": metric, "timing_threads": sorted(frame["timing_threads"].dropna().astype(int).unique().tolist())
        if "timing_threads" in frame else [],
        "sources": source_info, "input_rows": sum(source["rows"] for source in source_info) if source_info else None,
        "unique_queries": len(detail),
        "method": {
            "speedup": "OFF / ON from original unrounded timing pairs; values > 1 mean faster",
            "eligibility": "Correct, not marked TIMEOUT, finite positive OFF, ON, and ratio",
            "deduplication": "Final rows win family + query duplicates; attempts fill missing queries",
            "geomean": "exp(mean(log(OFF / ON))), each eligible query weighted equally",
            "total_speedup": "sum(OFF) / sum(ON) over the same eligible pairs, not mean query speedup",
            "stddev_variance": "Sample statistics (ddof=1); unavailable for n < 2",
            "percentiles": "Linear interpolation; p50 is median",
            "excluded": "No timeout substitution, imputation, trimming, or use of the representative display sample",
            "uncertainty": "Descriptive query-level statistics, not confidence intervals over repeated runs",
        },
        "groups": groups,
        "queries": json.loads(detail.to_json(orient="records", double_precision=15)),
    }


def markdown_report(report: dict) -> str:
    def number(value):
        return "NA" if value is None else f"{value:.6f}"

    lines = ["# Benchmark statistics", "", f"Run: `{report['run']}`. Metric: `{report['metric']}`. "
             f"Timing threads: {report['timing_threads'] or 'legacy / unspecified'}.", "",
             "## Definitions and coverage", ""]
    lines.extend(f"- {name}: {definition}." for name, definition in report["method"].items())
    lines.extend(["", f"Unique queries after final/attempts reconciliation: {report['unique_queries']}.", ""])
    family_order = {name: index for index, name in enumerate(("all", "graph", "TPC-H", "TPC-DS", "JOB"))}
    for subset in ("all", "outeryan_selected", "duckdb_selected"):
        rows = [row for row in report["groups"] if row["subset"] == subset and row["scope"] in ("overall", "benchmark")]
        rows.sort(key=lambda row: family_order[row["family"]])
        lines.extend([f"## {subset}", "", "### Speed-up distribution", "",
                      "| Benchmark | Valid / total | Min | Max | Geomean | Mean | Median | Sample SD | Total-time speed-up |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for row in rows:
            stats, counts = row["speedup"], row["counts"]
            values = [stats[key] for key in ("min", "max", "geomean", "mean", "median", "stddev")]
            lines.append(f"| {row['family']} | {counts['valid']} / {counts['total']} | " +
                         " | ".join(number(value) for value in values + [row["totals"]["speedup"]]) + " |")
        lines.extend(["", "### Percentiles and dispersion", "",
                      "| Benchmark | P05 | P10 | P25 | P75 | P90 | P95 | P99 | Variance | CV |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for row in rows:
            lines.append(f"| {row['family']} | " + " | ".join(number(row["speedup"][key]) for key in
                         ("p05", "p10", "p25", "p75", "p90", "p95", "p99", "variance", "cv")) + " |")
        lines.extend(["", "### Coverage and faster/slower counts", "",
                      "Faster/slower use exact OFF/ON > 1 or < 1. The ±5% band below applies to the speed-up ratio; "
                      "it is a descriptive band, not a statistical significance test.", "",
                      "| Benchmark | Timeout | Other excluded | Faster | Equal | Slower | >1.05 | [0.95,1.05] | <0.95 | >=2 | >=10 |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for row in rows:
            counts = row["counts"]
            values = [counts["timeouts"], counts["excluded"] - counts["timeouts"]] + [counts[key] for key in
                      ("faster", "equal", "slower", "speedup_gt_1_05", "speedup_in_0_95_to_1_05",
                       "speedup_lt_0_95", "speedup_ge_2", "speedup_ge_10")]
            lines.append(f"| {row['family']} | " + " | ".join(map(str, values)) + " |")
        lines.extend(["", "### Paired runtime totals (seconds)", "",
                      "| Benchmark | OFF total | ON total | Saved seconds | Time reduction (%) |",
                      "|---|---:|---:|---:|---:|"])
        for row in rows:
            totals = row["totals"]
            reduction = totals["time_reduction_fraction"]
            lines.append(f"| {row['family']} | " + " | ".join(number(value) for value in
                         (totals["off_s"], totals["on_s"], totals["saved_s"],
                          reduction * 100 if reduction is not None else None)) + " |")
        lines.extend(["", "### OFF/ON runtime distributions (seconds)", "",
                      "| Benchmark | Mode | Min | Max | Geomean | Mean | Median | Sample SD | P95 |",
                      "|---|---|---:|---:|---:|---:|---:|---:|---:|"])
        for row in rows:
            for mode in ("off_s", "on_s"):
                lines.append(f"| {row['family']} | {mode} | " + " | ".join(number(row[mode][key]) for key in
                             ("min", "max", "geomean", "mean", "median", "stddev", "p95")) + " |")
        lines.extend(["", "### Shape breakdown", "",
                      "| Benchmark | Shape | Valid / total | Min | Max | Geomean | Mean | Median | Total-time speed-up |",
                      "|---|---|---:|---:|---:|---:|---:|---:|---:|"])
        for row in report["groups"]:
            if row["subset"] == subset and row["scope"] in ("shape", "benchmark_shape"):
                values = [row["speedup"][key] for key in ("min", "max", "geomean", "mean", "median")]
                lines.append(f"| {row['family']} | {row['topology']} | {row['counts']['valid']} / "
                             f"{row['counts']['total']} | " + " | ".join(number(value) for value in
                             values + [row["totals"]["speedup"]]) + " |")
        lines.extend(["", "### Extreme queries", ""])
        for row in rows:
            for extreme in ("min", "max"):
                names = ", ".join(f"`{query}`" for query in row["speedup"][f"{extreme}_queries"]) or "NA"
                lines.append(f"- {row['family']} {extreme} = {number(row['speedup'][extreme])}: {names}.")
        lines.append("")
    lines.extend(["## Excluded queries", "", "| Benchmark | Query | Reason | Recorded note |", "|---|---|---|---|"])
    for row in report["queries"]:
        if not row["valid_timing"]:
            note = str(row.get("note") or "").replace("|", "/").replace("\n", " ")
            lines.append(f"| {row['family']} | `{row['query']}` | {row['exclusion_reason']} | {note} |")
    lines.extend(["", "## Sources", ""])
    for source in report["sources"]:
        lines.append(f"- [{Path(source['path']).name}]({source['path']}): {source['rows']} {source['kind']} rows; "
                     f"SHA-256 `{source['sha256']}`.")
    lines.extend(["", "The companion statistics.json contains every statistic for every group, plus all deduplicated "
                  "query timings and exclusion reasons. Values are rounded to six decimals only in this Markdown view.", ""])
    return "\n".join(lines)


def write_statistics(output_directory: Path, frame: pd.DataFrame, metric: str = "tm",
                     sources: list[str] | None = None) -> dict:
    report = build_statistics(frame, metric, sources)
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "statistics.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output_directory / "STATISTICS.md").write_text(markdown_report(report), encoding="utf-8")
    return report
