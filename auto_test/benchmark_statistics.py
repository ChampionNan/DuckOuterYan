#!/usr/bin/env python3
"""Descriptive ON/OFF statistics for a deduplicated, single-thread-setting run.

Keep failed and incomplete queries for coverage accounting. Measured timing
statistics use correct queries with finite positive OFF/ON pairs. DuckDB
fallbacks and aggregate queries without a realized aggregate pushdown are not
executed; they contribute the explicit selection-policy speed-up default 1.0
to speed-up distributions, but not runtime totals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


PHASE_COMPONENTS = (
    ("round1", "profile_round1_operator_s"),
    ("round2", "profile_round2_operator_s"),
    ("round3", "profile_round3_operator_s"),
    ("other", "profile_other_elapsed_s"),
)

FAMILY_LABELS = {
    "all": "all",
    "graph": "Graph",
    "tpch": "TPC-H",
    "tpc-h": "TPC-H",
    "tpcds": "TPC-DS",
    "tpc-ds": "TPC-DS",
    "job": "JOB",
}


def normalize_family(value: object) -> str:
    text = str(value).strip()
    return FAMILY_LABELS.get(text.lower(), text)


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
    identity_columns = [column for column in ("workload_category", "family", "query") if column in frame]
    if frame.duplicated(identity_columns).any():
        raise ValueError("deduplicate final and attempts rows before computing statistics")
    columns = [column for column in (
        "experiment_group", "corpus_version", "corpus_scope", "workload_category", "query_class",
        "query", "family", "topology", "workload_component", "source_component", "evaluation_role",
        "aggregate_query", "aggregate_pushdown_applied", "selected_plan", "correct", "note", "timing_status",
        "timing_threads", "sql_path",
    ) if column in frame]
    detail = frame[columns].copy().reset_index(drop=True)
    detail["family"] = detail["family"].map(normalize_family)
    detail["selected_plan"] = detail.get("selected_plan", pd.Series("UNKNOWN", index=detail.index)).fillna(
        "UNKNOWN").astype(str).str.upper()
    correct = detail.get("correct", pd.Series("TRUE", index=detail.index)).astype(str).str.upper().eq("TRUE")
    notes = detail.get("note", pd.Series("", index=detail.index)).fillna("").astype(str)
    timing_status = detail.get(
        "timing_status", pd.Series("", index=detail.index)
    ).fillna("").astype(str).str.lower()
    missing = pd.Series(np.nan, index=frame.index)
    off = pd.to_numeric(frame.get(f"{metric}_off", missing), errors="coerce").reset_index(drop=True)
    on = pd.to_numeric(frame.get(f"{metric}_on", missing), errors="coerce").reset_index(drop=True)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore", under="ignore"):
        speedup = off / on
    pair = np.isfinite(off) & off.gt(0) & np.isfinite(on) & on.gt(0)
    timeout = notes.str.contains("TIMEOUT", case=False, regex=False)
    measured = correct & ~timeout & pair & np.isfinite(speedup) & speedup.gt(0)
    fallback = timing_status.eq("fallback-skip") | notes.str.upper().eq("FALLBACK-SKIP")
    valid = measured | fallback
    detail["off_s"], detail["on_s"] = off, on
    detail["speedup"] = speedup.where(measured).mask(fallback, 1.0)
    detail["valid_timing"] = measured
    detail["valid_speedup"] = valid
    detail["speedup_source"] = np.where(fallback, "fallback-default", np.where(measured, "measured", ""))
    # Exclusive reasons make coverage totals reconcile without double-counting.
    detail["exclusion_reason"] = np.select(
        [valid, timeout, ~correct, ~pair],
        ["", "timeout", "correctness_not_true", "missing_or_invalid_timing"],
        default="nonfinite_or_nonpositive_ratio",
    )
    return detail


def summarize(rows: pd.DataFrame) -> dict:
    valid = rows.loc[rows["valid_speedup"]]
    measured = rows.loc[rows["valid_timing"]]
    speedup = valid["speedup"]
    counts = {
        "total": len(rows), "valid": len(valid), "excluded": len(rows) - len(valid),
        "measured": len(measured),
        "fallback_skips": int(valid["speedup_source"].eq("fallback-default").sum()),
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
    total_off = float(measured["off_s"].sum()) if len(measured) else None
    total_on = float(measured["on_s"].sum()) if len(measured) else None
    stats = distribution(speedup)
    for name in ("min", "max"):
        stats[f"{name}_queries"] = sorted(valid.loc[speedup.eq(stats[name]), "query"].tolist())
    return {
        "counts": counts, "speedup": stats,
        "off_s": distribution(measured["off_s"]), "on_s": distribution(measured["on_s"]),
        "totals": {"off_s": total_off, "on_s": total_on,
                   "speedup": total_off / total_on if total_on is not None else None,
                   "saved_s": total_off - total_on if total_on is not None else None,
                   "time_reduction_fraction": 1 - total_on / total_off if total_off is not None else None},
    }


def build_phase_statistics(frame: pd.DataFrame, metric: str) -> dict:
    """Summarize complete same-run phase profiles without treating CPU work as wall time."""
    required = {
        "query", "family", "selected_plan", "profile_status", "profile_wall_time_s",
        "profile_cpu_time_s", *(column for _, column in PHASE_COMPONENTS),
    }
    if not required.issubset(frame.columns):
        return {
            "available": False,
            "reason": "input has no complete phase-profile schema",
            "method": {},
            "groups": [],
            "queries": [],
        }

    detail = frame[[column for column in (
        "experiment_group", "corpus_version", "corpus_scope", "workload_category", "query_class",
        "query", "family", "topology", "selected_plan", "correct", "note",
        "profile_status", "profile_threads",
        "profile_wall_time_s", "profile_cpu_time_s", *(column for _, column in PHASE_COMPONENTS),
        f"{metric}_off", f"{metric}_on",
    ) if column in frame]].copy().reset_index(drop=True)
    detail["family"] = detail["family"].map(normalize_family)
    numeric_columns = [
        "profile_threads", "profile_wall_time_s", "profile_cpu_time_s",
        *(column for _, column in PHASE_COMPONENTS), f"{metric}_off", f"{metric}_on",
    ]
    for column in numeric_columns:
        if column in detail:
            detail[column] = pd.to_numeric(detail[column], errors="coerce")
    selected = detail["selected_plan"].fillna("").astype(str).str.upper().eq("OUTERYAN")
    complete = detail["profile_status"].fillna("").astype(str).str.upper().eq("OK")
    correct = detail.get("correct", pd.Series("TRUE", index=detail.index)).astype(str).str.upper().eq("TRUE")
    notes = detail.get("note", pd.Series("", index=detail.index)).fillna("").astype(str)
    not_timeout = ~notes.str.contains("TIMEOUT", case=False, regex=False)
    finite = np.isfinite(detail["profile_wall_time_s"]) & detail["profile_wall_time_s"].gt(0)
    finite &= np.isfinite(detail["profile_cpu_time_s"]) & detail["profile_cpu_time_s"].gt(0)
    for _, column in PHASE_COMPONENTS:
        finite &= np.isfinite(detail[column]) & detail[column].ge(0)
    detail = detail.loc[selected & complete & correct & not_timeout & finite].copy()
    if detail.empty:
        return {
            "available": False,
            "reason": "no complete OuterYan-selected phase profiles",
            "method": {},
            "groups": [],
            "queries": [],
        }

    detail["phase_sum_s"] = sum(detail[column] for _, column in PHASE_COMPONENTS)
    tolerance = np.maximum(1e-9, detail["profile_cpu_time_s"].abs() * 1e-8)
    consistent = (detail["phase_sum_s"] - detail["profile_cpu_time_s"]).abs().le(tolerance)
    detail = detail.loc[consistent].copy()
    if detail.empty:
        return {
            "available": False,
            "reason": "phase components do not reconcile with profiled CPU time",
            "method": {},
            "groups": [],
            "queries": [],
        }

    for name, column in PHASE_COMPONENTS:
        detail[f"{name}_fraction"] = detail[column] / detail["profile_cpu_time_s"]
    off_column, on_column = f"{metric}_off", f"{metric}_on"
    if off_column in detail and on_column in detail:
        valid_pair = (
            np.isfinite(detail[off_column]) & detail[off_column].gt(0)
            & np.isfinite(detail[on_column]) & detail[on_column].gt(0)
        )
        detail["unprofiled_speedup"] = (detail[off_column] / detail[on_column]).where(valid_pair)
    else:
        detail["unprofiled_speedup"] = np.nan

    def phase_group(scope: str, rows: pd.DataFrame, *, family: str = "all",
                    workload_category: str = "all") -> dict:
        cpu_total = float(rows["profile_cpu_time_s"].sum())
        component_seconds = {
            name: float(rows[column].sum()) for name, column in PHASE_COMPONENTS
        }
        speedups = rows["unprofiled_speedup"].dropna()
        valid_pairs = rows.loc[rows["unprofiled_speedup"].notna()]
        return {
            "scope": scope,
            "family": family,
            "workload_category": workload_category,
            "profiles": len(rows),
            "profile_threads": sorted(rows["profile_threads"].dropna().astype(int).unique().tolist())
            if "profile_threads" in rows else [],
            "cpu_total_s": cpu_total,
            "component_seconds": component_seconds,
            "component_seconds_distribution": {
                name: signed_distribution(rows[column]) for name, column in PHASE_COMPONENTS
            },
            "cpu_weighted_fraction": {
                name: value / cpu_total for name, value in component_seconds.items()
            },
            "median_query_fraction": {
                name: float(rows[f"{name}_fraction"].median()) for name, _ in PHASE_COMPONENTS
            },
            "query_fraction_distribution": {
                name: signed_distribution(rows[f"{name}_fraction"])
                for name, _ in PHASE_COMPONENTS
            },
            "profile_wall_s": distribution(rows["profile_wall_time_s"]),
            "unprofiled_speedup": distribution(speedups),
            "unprofiled_total_speedup": (
                float(valid_pairs[off_column].sum() / valid_pairs[on_column].sum())
                if len(valid_pairs) else None
            ),
        }

    groups = [phase_group("overall", detail)]
    groups.extend(
        phase_group("benchmark", rows, family=family)
        for family, rows in detail.groupby("family", sort=True)
    )
    if "workload_category" in detail:
        groups.extend(
            phase_group("workload_category", rows, workload_category=category)
            for category, rows in detail.groupby("workload_category", sort=True)
        )
        groups.extend(
            phase_group("workload_benchmark", rows, family=family, workload_category=category)
            for (category, family), rows in detail.groupby(["workload_category", "family"], sort=True)
        )
    query_columns = [column for column in (
        "experiment_group", "corpus_version", "corpus_scope", "workload_category", "query_class",
        "query", "family", "topology", "profile_threads", "profile_wall_time_s",
        "profile_cpu_time_s", "phase_sum_s", "unprofiled_speedup",
        *(column for _, column in PHASE_COMPONENTS),
        *(f"{name}_fraction" for name, _ in PHASE_COMPONENTS),
    ) if column in detail]
    return {
        "available": True,
        "reason": None,
        "method": {
            "population": "Correct, non-timeout queries with complete same-run profiles whose ON run selected OuterYan",
            "components": "Accumulated operator CPU seconds; components sum to profile_cpu_time_s",
            "wall_time": "profile_wall_time_s is elapsed latency and is not added to CPU components",
            "cpu_weighted_fraction": "sum(component CPU seconds) / sum(profile CPU seconds)",
            "median_query_fraction": "median of each query's component / profile CPU time",
            "speedup": "Unprofiled OFF / ON timing for the same queries",
        },
        "groups": groups,
        "queries": json.loads(detail[query_columns].to_json(orient="records", double_precision=15)),
    }


def signed_distribution(values: pd.Series) -> dict:
    """Distribution for differences, where a geometric mean is undefined."""
    values = values.dropna()
    if values.empty:
        return dict.fromkeys(("min", "max", "mean", "median", "stddev"))
    return {
        "min": float(values.min()),
        "max": float(values.max()),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "stddev": float(values.std(ddof=1)) if len(values) > 1 else None,
    }


def build_optimizer_statistics(frame: pd.DataFrame) -> dict:
    """Summarize paired execution profiles and algorithmic optimizer phases."""
    required = {
        "query", "family", "selected_plan", "correct", "note", "optimizer_profile_status",
        "optimizer_duckdb_total_s", "optimizer_outeryan_total_s",
        "optimizer_duckdb_phases_json", "optimizer_outeryan_phases_json",
    }
    if not required.issubset(frame.columns):
        return {
            "available": False,
            "reason": "input has no complete optimizer-profile schema",
            "method": {},
            "groups": [],
            "queries": [],
            "phases": [],
        }

    columns = [column for column in (
        "experiment_group", "corpus_version", "corpus_scope", "workload_category", "query_class",
        "query", "family", "selected_plan", "correct", "note", "optimizer_profile_status",
        "optimizer_timed_samples", "optimizer_duckdb_total_s", "optimizer_outeryan_total_s",
        "optimizer_overhead_s", "optimizer_outeryan_to_duckdb_ratio",
        "optimizer_duckdb_measured_phase_s", "optimizer_outeryan_measured_phase_s",
        "optimizer_duckdb_other_s", "optimizer_outeryan_other_s",
        "optimizer_duckdb_phases_json", "optimizer_outeryan_phases_json", "optimizer_phase_delta_json",
    ) if column in frame]
    detail = frame[columns].copy().reset_index(drop=True)
    detail["family"] = detail["family"].map(normalize_family)
    numeric = [column for column in (
        "optimizer_timed_samples", "optimizer_duckdb_total_s", "optimizer_outeryan_total_s",
        "optimizer_overhead_s", "optimizer_outeryan_to_duckdb_ratio",
        "optimizer_duckdb_measured_phase_s", "optimizer_outeryan_measured_phase_s",
        "optimizer_duckdb_other_s", "optimizer_outeryan_other_s",
    ) if column in detail]
    for column in numeric:
        detail[column] = pd.to_numeric(detail[column], errors="coerce")
    correct = detail["correct"].astype(str).str.upper().eq("TRUE")
    not_timeout = ~detail["note"].fillna("").astype(str).str.contains("TIMEOUT", case=False, regex=False)
    complete = detail["optimizer_profile_status"].fillna("").astype(str).str.upper().eq("OK")
    finite = (
        np.isfinite(detail["optimizer_duckdb_total_s"])
        & detail["optimizer_duckdb_total_s"].gt(0)
        & np.isfinite(detail["optimizer_outeryan_total_s"])
        & detail["optimizer_outeryan_total_s"].gt(0)
    )
    detail = detail.loc[correct & not_timeout & complete & finite].copy()
    if detail.empty:
        return {
            "available": False,
            "reason": "no correct non-timeout queries have complete paired optimizer profiles",
            "method": {},
            "groups": [],
            "queries": [],
            "phases": [],
        }

    detail["optimizer_overhead_s"] = (
        detail["optimizer_outeryan_total_s"] - detail["optimizer_duckdb_total_s"]
    )
    detail["optimizer_outeryan_to_duckdb_ratio"] = (
        detail["optimizer_outeryan_total_s"] / detail["optimizer_duckdb_total_s"]
    )
    parsed_phases = []
    valid_indices = []
    for index, row in detail.iterrows():
        try:
            row_phases = []
            off_phases = json.loads(row["optimizer_duckdb_phases_json"])
            on_phases = json.loads(row["optimizer_outeryan_phases_json"])
            if not isinstance(off_phases, dict) or not isinstance(on_phases, dict):
                raise ValueError("optimizer phase JSON is not an object")
            phase_names = sorted(set(off_phases) | set(on_phases))
            for phase in phase_names:
                off = float(off_phases.get(phase, 0.0))
                on = float(on_phases.get(phase, 0.0))
                if not math.isfinite(off) or not math.isfinite(on) or off < 0 or on < 0:
                    raise ValueError("invalid optimizer phase value")
                row_phases.append({
                    "row_index": int(index),
                    "experiment_group": row.get("experiment_group"),
                    "corpus_version": row.get("corpus_version"),
                    "corpus_scope": row.get("corpus_scope"),
                    "workload_category": row.get("workload_category"),
                    "query_class": row.get("query_class"),
                    "query": row["query"],
                    "family": row["family"],
                    "selected_plan": str(row["selected_plan"]).upper(),
                    "phase": phase,
                    "duckdb_s": off,
                    "outeryan_s": on,
                    "delta_s": on - off,
                })
            parsed_phases.extend(row_phases)
            valid_indices.append(index)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    detail = detail.loc[valid_indices].copy()
    if detail.empty:
        return {
            "available": False,
            "reason": "optimizer totals exist but workflow-phase JSON is invalid",
            "method": {},
            "groups": [],
            "queries": [],
            "phases": [],
        }

    def optimizer_group(subset: str, scope: str, rows: pd.DataFrame, *, family: str = "all",
                        workload_category: str = "all") -> dict:
        off_total = float(rows["optimizer_duckdb_total_s"].sum())
        on_total = float(rows["optimizer_outeryan_total_s"].sum())
        return {
            "subset": subset,
            "scope": scope,
            "family": family,
            "workload_category": workload_category,
            "profiles": len(rows),
            "duckdb_s": distribution(rows["optimizer_duckdb_total_s"]),
            "outeryan_s": distribution(rows["optimizer_outeryan_total_s"]),
            "overhead_s": signed_distribution(rows["optimizer_overhead_s"]),
            "outeryan_to_duckdb_ratio": distribution(rows["optimizer_outeryan_to_duckdb_ratio"]),
            "totals": {
                "duckdb_s": off_total,
                "outeryan_s": on_total,
                "overhead_s": on_total - off_total,
                "outeryan_to_duckdb_ratio": on_total / off_total if off_total > 0 else None,
            },
        }

    groups = []
    for subset, rows in (
        ("all", detail),
        ("outeryan_selected", detail.loc[detail["selected_plan"].astype(str).str.upper().eq("OUTERYAN")]),
    ):
        groups.append(optimizer_group(subset, "overall", rows))
        groups.extend(
            optimizer_group(subset, "benchmark", group, family=family)
            for family, group in rows.groupby("family", sort=True)
        )
        if "workload_category" in rows:
            groups.extend(
                optimizer_group(subset, "workload_category", group, workload_category=category)
                for category, group in rows.groupby("workload_category", sort=True)
            )
            groups.extend(
                optimizer_group(subset, "workload_benchmark", group, family=family,
                                workload_category=category)
                for (category, family), group in rows.groupby(["workload_category", "family"], sort=True)
            )

    query_columns = [column for column in columns if not column.endswith("_phases_json")]
    return {
        "available": True,
        "reason": None,
        "method": {
            "population": "Correct, non-timeout queries with complete paired detailed optimizer profiles",
            "measurement": "Real query execution; one unprofiled warm-up plus one profiled sample per side",
            "selection": "The sole post-warm-up execution supplies optimizer totals and workflow phases",
            "total": "DuckDB all_optimizers wall time from the execution profile",
            "phases": "Algorithmic OuterYan workflow phases; generic DuckDB per-pass timings are not exported",
            "ratio": "OuterYan optimizer time / DuckDB optimizer time; values above 1 are overhead",
        },
        "groups": groups,
        "queries": json.loads(detail[query_columns].to_json(orient="records", double_precision=15)),
        "phases": parsed_phases,
    }


def build_statistics(frame: pd.DataFrame, metric: str = "tm", sources: list[str] | None = None) -> dict:
    detail = prepare_queries(frame, metric)
    groups = []
    for subset, rows in (("all", detail),
                         ("outeryan_selected", detail.loc[detail["selected_plan"].eq("OUTERYAN")]),
                         ("duckdb_selected", detail.loc[detail["selected_plan"].eq("DUCKDB")])):
        groups.append({"subset": subset, "scope": "overall", "family": "all", "topology": "all",
                       **summarize(rows)})
        group_specs = [("benchmark", ["family"])]
        if "topology" in detail:
            group_specs.extend([("shape", ["topology"]), ("benchmark_shape", ["family", "topology"])])
        if "workload_component" in detail:
            group_specs.append(("workload_component", ["workload_component"]))
        if "workload_category" in detail:
            group_specs.extend([
                ("workload_category", ["workload_category"]),
                ("workload_benchmark", ["workload_category", "family"]),
            ])
        for scope, keys in group_specs:
            for group_keys, group_rows in rows.groupby(keys, sort=True):
                if not isinstance(group_keys, tuple):
                    group_keys = (group_keys,)
                identity = dict(zip(keys, group_keys))
                groups.append({
                    "subset": subset,
                    "scope": scope,
                    "family": identity.get("family", "all"),
                    "topology": identity.get("topology", "all"),
                    "workload_component": identity.get("workload_component", "all"),
                    "workload_category": identity.get("workload_category", "all"),
                    **summarize(group_rows),
                })
    source_info = []
    for source in sources or []:
        path = Path(source).resolve()
        source_info.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "rows": len(pd.read_csv(path)),
                            "kind": "attempts" if path.name.endswith(".attempts.csv") else "final"})
    return {
        "schema_version": 2,
        "run": (
            str(frame["run"].iloc[0]) if "run" in frame and len(frame)
            else str(frame["experiment_group"].iloc[0]) if "experiment_group" in frame and len(frame)
            else None
        ),
        "metric": metric, "timing_threads": sorted(frame["timing_threads"].dropna().astype(int).unique().tolist())
        if "timing_threads" in frame else [],
        "sources": source_info, "input_rows": sum(source["rows"] for source in source_info) if source_info else None,
        "unique_queries": len(detail),
        "method": {
            "speedup": "Measured rows use OFF / ON from original unrounded timing pairs; values > 1 mean faster",
            "eligibility": "Measured rows require correct, non-timeout finite positive OFF/ON pairs; DuckDB fallbacks and aggregate queries without a realized pushdown contribute the explicit policy default 1.0",
            "fallback": "timing_status=fallback-skip means no query execution occurred; speed-up 1.0 is a selection-policy default, not a measurement",
            "deduplication": "Rows are unique by workload category + family + query",
            "geomean": "exp(mean(log(OFF / ON))), each eligible query weighted equally",
            "total_speedup": "sum(OFF) / sum(ON) over measured timing pairs only; fallback skips have no fabricated runtime",
            "stddev_variance": "Sample statistics (ddof=1); unavailable for n < 2",
            "percentiles": "Linear interpolation; p50 is median",
            "excluded": "No timeout substitution, runtime imputation, speed-up trimming, or use of the representative display sample",
            "uncertainty": "Descriptive query-level statistics, not confidence intervals over repeated runs",
        },
        "groups": groups,
        "phase_profiles": build_phase_statistics(frame, metric),
        "optimizer_profiles": build_optimizer_statistics(frame),
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
    family_order = {name: index for index, name in enumerate(("all", "Graph", "TPC-H", "TPC-DS", "JOB"))}
    for subset in ("all", "outeryan_selected", "duckdb_selected"):
        rows = [row for row in report["groups"] if row["subset"] == subset and row["scope"] in ("overall", "benchmark")]
        rows.sort(key=lambda row: family_order[row["family"]])
        lines.extend([f"## {subset}", "", "### Speed-up distribution", "",
                      "| Benchmark | Speed-ups / total | Measured | Fallback default | Min | Max | Geomean | Mean | Median | Sample SD | Total-time speed-up |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for row in rows:
            stats, counts = row["speedup"], row["counts"]
            values = [stats[key] for key in ("min", "max", "geomean", "mean", "median", "stddev")]
            lines.append(f"| {row['family']} | {counts['valid']} / {counts['total']} | "
                         f"{counts['measured']} | {counts['fallback_skips']} | " +
                         " | ".join(number(value) for value in values + [row["totals"]["speedup"]]) + " |")
        lines.extend(["", "### Percentiles and dispersion", "",
                      "| Benchmark | P05 | P10 | P25 | P75 | P90 | P95 | P99 | Variance | CV |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for row in rows:
            lines.append(f"| {row['family']} | " + " | ".join(number(row["speedup"][key]) for key in
                         ("p05", "p10", "p25", "p75", "p90", "p95", "p99", "variance", "cv")) + " |")
        lines.extend(["", "### Coverage and faster/slower counts", "",
                      "Measured faster/slower use exact OFF/ON; fallback skips contribute exactly 1.0. "
                      "The ±5% band below applies to the speed-up ratio; "
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
        component_rows = [row for row in report["groups"]
                          if row["subset"] == subset and row["scope"] == "workload_component"]
        if component_rows:
            lines.extend(["", "### Workload-component breakdown", "",
                          "| Component | Valid / total | Geomean | Mean | Median | Max | Total-time speed-up |",
                          "|---|---:|---:|---:|---:|---:|---:|"])
            for row in component_rows:
                stats, counts = row["speedup"], row["counts"]
                values = [stats[key] for key in ("geomean", "mean", "median", "max")]
                lines.append(
                    f"| {row['workload_component']} | {counts['valid']} / {counts['total']} | "
                    + " | ".join(number(value) for value in values + [row["totals"]["speedup"]])
                    + " |"
                )
        lines.extend(["", "### Extreme queries", ""])
        for row in rows:
            for extreme in ("min", "max"):
                names = ", ".join(f"`{query}`" for query in row["speedup"][f"{extreme}_queries"]) or "NA"
                lines.append(f"- {row['family']} {extreme} = {number(row['speedup'][extreme])}: {names}.")
        lines.append("")
    phase = report["phase_profiles"]
    lines.extend(["## Phase-profile statistics", ""])
    if not phase["available"]:
        lines.extend([f"Unavailable: {phase['reason']}.", ""])
    else:
        lines.extend(f"- {name}: {definition}." for name, definition in phase["method"].items())
        lines.extend(["", "CPU shares below are work-weighted across the displayed population; they are not wall-time shares.", "",
                      "| Benchmark | Profiles | Round 1 CPU (%) | Round 2 CPU (%) | Round 3 CPU (%) | Other CPU (%) | Median unprofiled speed-up | Total-time speed-up |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|"])
        phase_order = {name: index for index, name in enumerate(("all", "Graph", "TPC-H", "TPC-DS", "JOB"))}
        phase_headline = [row for row in phase["groups"] if row["scope"] in ("overall", "benchmark")]
        for row in sorted(phase_headline, key=lambda item: phase_order.get(item["family"], 99)):
            shares = row["cpu_weighted_fraction"]
            median = row["unprofiled_speedup"]["median"]
            values = [shares[name] * 100 for name, _ in PHASE_COMPONENTS]
            lines.append(
                f"| {row['family']} | {row['profiles']} | "
                + " | ".join(number(value) for value in values + [median, row["unprofiled_total_speedup"]])
                + " |"
            )
        lines.append("")
    optimizer = report["optimizer_profiles"]
    lines.extend(["## Optimization-time statistics", ""])
    if not optimizer["available"]:
        lines.extend([f"Unavailable: {optimizer['reason']}.", ""])
    else:
        lines.extend(f"- {name}: {definition}." for name, definition in optimizer["method"].items())
        for subset in ("all", "outeryan_selected"):
            rows = [row for row in optimizer["groups"]
                    if row["subset"] == subset and row["scope"] in ("overall", "benchmark")]
            rows.sort(key=lambda row: family_order.get(row["family"], 99))
            lines.extend(["", f"### {subset}", "",
                          "| Benchmark | Profiles | DuckDB median (s) | OuterYan median (s) | Median ratio | Sample SD ratio | Total DuckDB (s) | Total OuterYan (s) | Total ratio |",
                          "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
            for row in rows:
                values = (
                    row["duckdb_s"]["median"], row["outeryan_s"]["median"],
                    row["outeryan_to_duckdb_ratio"]["median"],
                    row["outeryan_to_duckdb_ratio"]["stddev"],
                    row["totals"]["duckdb_s"], row["totals"]["outeryan_s"],
                    row["totals"]["outeryan_to_duckdb_ratio"],
                )
                lines.append(f"| {row['family']} | {row['profiles']} | "
                             + " | ".join(number(value) for value in values) + " |")
        lines.extend(["", "Per-query workflow timings and their DuckDB-to-OuterYan deltas are in "
                      "`optimizer_phases.csv`; group-level phase summaries are in `optimizer_phase_summary.csv`.", ""])
    lines.extend(["## Excluded queries", "", "| Benchmark | Query | Reason | Recorded note |", "|---|---|---|---|"])
    for row in report["queries"]:
        if not row["valid_speedup"]:
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
    benchmark_rows = []
    for row in report["groups"]:
        if row["subset"] not in ("all", "outeryan_selected"):
            continue
        if row["scope"] not in ("overall", "benchmark", "workload_category", "workload_benchmark"):
            continue
        benchmark_rows.append({
            "subset": row["subset"],
            "scope": row["scope"],
            "workload_category": row.get("workload_category", "all"),
            "benchmark": row["family"],
            "valid": row["counts"]["valid"],
            "measured": row["counts"]["measured"],
            "fallback_skips": row["counts"]["fallback_skips"],
            "total": row["counts"]["total"],
            "excluded": row["counts"]["excluded"],
            "timeouts": row["counts"]["timeouts"],
            "min": row["speedup"]["min"],
            "max": row["speedup"]["max"],
            "geomean": row["speedup"]["geomean"],
            "mean": row["speedup"]["mean"],
            "median": row["speedup"]["median"],
            "stddev": row["speedup"]["stddev"],
            "duckdb_total_s": row["totals"]["off_s"],
            "outeryan_total_s": row["totals"]["on_s"],
            "total_time_speedup": row["totals"]["speedup"],
        })
    pd.DataFrame(benchmark_rows).to_csv(output_directory / "benchmark_statistics.csv", index=False)

    phase_rows = []
    phase = report["phase_profiles"]
    if phase["available"]:
        for row in phase["groups"]:
            phase_rows.append({
                "scope": row["scope"],
                "workload_category": row.get("workload_category", "all"),
                "benchmark": row["family"],
                "profiles": row["profiles"],
                "profile_threads": ";".join(map(str, row["profile_threads"])),
                "cpu_total_s": row["cpu_total_s"],
                **{f"{name}_total_s": row["component_seconds"][name] for name, _ in PHASE_COMPONENTS},
                **{f"{name}_s_{stat}": row["component_seconds_distribution"][name][stat]
                   for name, _ in PHASE_COMPONENTS for stat in ("min", "max", "mean", "median", "stddev")},
                **{f"{name}_cpu_fraction": row["cpu_weighted_fraction"][name] for name, _ in PHASE_COMPONENTS},
                **{f"{name}_median_query_fraction": row["median_query_fraction"][name]
                   for name, _ in PHASE_COMPONENTS},
                **{f"{name}_query_fraction_{stat}": row["query_fraction_distribution"][name][stat]
                   for name, _ in PHASE_COMPONENTS for stat in ("min", "max", "mean", "median", "stddev")},
                "profile_wall_median_s": row["profile_wall_s"]["median"],
                "unprofiled_speedup_median": row["unprofiled_speedup"]["median"],
                "unprofiled_total_speedup": row["unprofiled_total_speedup"],
            })
    phase_columns = [
        "scope", "workload_category", "benchmark", "profiles", "profile_threads", "cpu_total_s",
        *(f"{name}_total_s" for name, _ in PHASE_COMPONENTS),
        *(f"{name}_s_{stat}" for name, _ in PHASE_COMPONENTS
          for stat in ("min", "max", "mean", "median", "stddev")),
        *(f"{name}_cpu_fraction" for name, _ in PHASE_COMPONENTS),
        *(f"{name}_median_query_fraction" for name, _ in PHASE_COMPONENTS),
        *(f"{name}_query_fraction_{stat}" for name, _ in PHASE_COMPONENTS
          for stat in ("min", "max", "mean", "median", "stddev")),
        "profile_wall_median_s", "unprofiled_speedup_median", "unprofiled_total_speedup",
    ]
    pd.DataFrame(phase_rows, columns=phase_columns).to_csv(output_directory / "phase_summary.csv", index=False)

    optimizer_rows = []
    optimizer = report["optimizer_profiles"]
    if optimizer["available"]:
        for row in optimizer["groups"]:
            optimizer_rows.append({
                "subset": row["subset"],
                "scope": row["scope"],
                "workload_category": row.get("workload_category", "all"),
                "benchmark": row["family"],
                "profiles": row["profiles"],
                **{f"duckdb_{name}": row["duckdb_s"][name]
                   for name in ("min", "max", "geomean", "mean", "median", "stddev")},
                **{f"outeryan_{name}": row["outeryan_s"][name]
                   for name in ("min", "max", "geomean", "mean", "median", "stddev")},
                **{f"ratio_{name}": row["outeryan_to_duckdb_ratio"][name]
                   for name in ("min", "max", "geomean", "mean", "median", "stddev")},
                "duckdb_total_s": row["totals"]["duckdb_s"],
                "outeryan_total_s": row["totals"]["outeryan_s"],
                "overhead_total_s": row["totals"]["overhead_s"],
                "total_ratio": row["totals"]["outeryan_to_duckdb_ratio"],
            })
    optimizer_columns = [
        "subset", "scope", "workload_category", "benchmark", "profiles",
        *(f"duckdb_{name}" for name in ("min", "max", "geomean", "mean", "median", "stddev")),
        *(f"outeryan_{name}" for name in ("min", "max", "geomean", "mean", "median", "stddev")),
        *(f"ratio_{name}" for name in ("min", "max", "geomean", "mean", "median", "stddev")),
        "duckdb_total_s", "outeryan_total_s", "overhead_total_s", "total_ratio",
    ]
    pd.DataFrame(optimizer_rows, columns=optimizer_columns).to_csv(
        output_directory / "optimizer_summary.csv", index=False
    )

    phase_rows = optimizer["phases"] if optimizer["available"] else []
    phase_columns = [
        "experiment_group", "corpus_version", "corpus_scope", "workload_category", "query_class",
        "query", "family", "selected_plan", "phase", "duckdb_s", "outeryan_s", "delta_s",
    ]
    pd.DataFrame(phase_rows).drop(columns=["row_index"], errors="ignore").reindex(columns=phase_columns).to_csv(
        output_directory / "optimizer_phases.csv", index=False
    )
    phase_summary_rows = []
    if phase_rows:
        phase_frame = pd.DataFrame(phase_rows)
        for subset, subset_rows in (
            ("all", phase_frame),
            ("outeryan_selected", phase_frame.loc[phase_frame["selected_plan"].eq("OUTERYAN")]),
        ):
            group_specs = [("overall", ["phase"]), ("benchmark", ["family", "phase"])]
            if "workload_category" in subset_rows:
                group_specs.extend([
                    ("workload_category", ["workload_category", "phase"]),
                    ("workload_benchmark", ["workload_category", "family", "phase"]),
                ])
            for scope, keys in group_specs:
                for identity, rows in subset_rows.groupby(keys, sort=True):
                    if not isinstance(identity, tuple):
                        identity = (identity,)
                    labels = dict(zip(keys, identity))
                    phase_summary_rows.append({
                        "subset": subset,
                        "scope": scope,
                        "workload_category": labels.get("workload_category", "all"),
                        "benchmark": labels.get("family", "all"),
                        "phase": labels["phase"],
                        "profiles": len(rows),
                        **{f"duckdb_{name}": signed_distribution(rows["duckdb_s"])[name]
                           for name in ("mean", "median", "stddev")},
                        **{f"outeryan_{name}": signed_distribution(rows["outeryan_s"])[name]
                           for name in ("mean", "median", "stddev")},
                        **{f"delta_{name}": signed_distribution(rows["delta_s"])[name]
                           for name in ("mean", "median", "stddev")},
                    })
    phase_summary_columns = [
        "subset", "scope", "workload_category", "benchmark", "phase", "profiles",
        "duckdb_mean", "duckdb_median", "duckdb_stddev",
        "outeryan_mean", "outeryan_median", "outeryan_stddev",
        "delta_mean", "delta_median", "delta_stddev",
    ]
    pd.DataFrame(phase_summary_rows, columns=phase_summary_columns).to_csv(
        output_directory / "optimizer_phase_summary.csv", index=False
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Combine experiment CSVs and write benchmark statistics")
    parser.add_argument("sources", nargs="+", help="Per-corpus experiment CSV files")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--combined-csv", type=Path,
                        help="Optional path for a concatenated raw CSV")
    parser.add_argument("--run", required=True, help="Logical experiment-group identifier")
    parser.add_argument("--metric", choices=("tm", "t1"), default="tm")
    args = parser.parse_args(argv)

    frames = []
    expected_columns = None
    for source in args.sources:
        frame = pd.read_csv(source, keep_default_na=False)
        columns = list(frame.columns)
        if expected_columns is None:
            expected_columns = columns
        elif columns != expected_columns:
            raise ValueError(f"CSV schema mismatch: {source}")
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    if "experiment_group" not in combined:
        combined.insert(0, "experiment_group", args.run)
    elif not combined["experiment_group"].astype(str).eq(str(args.run)).all():
        raise ValueError("source CSVs do not belong to the requested experiment group")
    if args.combined_csv is not None:
        args.combined_csv.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(args.combined_csv, index=False)
    statistics_frame = combined.copy()
    statistics_frame["run"] = args.run
    write_statistics(args.output_dir, statistics_frame, args.metric, args.sources)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
