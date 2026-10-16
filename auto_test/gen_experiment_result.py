#!/usr/bin/env python3
"""Summarize experiment CSVs, render figures and generate paper tables in one step.

Usage: python3 auto_test/gen_experiment_result.py --date 20260926
Default output: auto_test/results/plots/20260926/. Multiple thread settings
remain separate under that date. Only catalog metadata is read from databases;
benchmark SQL is never executed.

The default cohort deduplicates SQL across all query types for the same date and
thread count; latest observations win, including failures. Historical versioned
CSV files are resolved through archived SQL and canonical aliases. Exclude a
measured pair only when both runtimes are strictly below 1 second by default;
--include-subsecond retains these pairs for review. Unexecuted
fallback placeholders are excluded from measured performance.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import glob
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import warnings

if __package__:
    from .benchmark_corpus import count_base_relations, historical_manifests, read_manifest, resolve_sql_path, sql_fingerprint
else:
    from benchmark_corpus import count_base_relations, historical_manifests, read_manifest, resolve_sql_path, sql_fingerprint

import numpy as np

def import_pandas():
    """Ignore an incomplete optional Arrow installation, without changing it on disk."""
    try:
        arrow = importlib.import_module("pyarrow")
    except ImportError:
        # pandas supports running without Arrow; NumPy and pandas remain required.
        pass
    else:
        if not isinstance(getattr(arrow, "__version__", None), str):
            warnings.warn(
                "Ignoring incomplete optional pyarrow installation: no __version__. "
                "CSV statistics use pandas/NumPy; Arrow is disabled for this process.",
                RuntimeWarning,
            )
            # pandas imports Arrow even for CSV work. Treat the malformed package
            # as unavailable rather than inventing a version or patching pandas.
            for name in list(sys.modules):
                if name == "pyarrow" or name.startswith("pyarrow."):
                    del sys.modules[name]
            sys.modules["pyarrow"] = None
    return importlib.import_module("pandas")


pd = import_pandas()


# ---- Shared statistics and eligibility --------------------------------------

MIN_RUNTIME_SECONDS = 1.0
TIMEOUT_SECONDS = 10 * 60


def below_runtime_threshold(frame: pd.DataFrame, metric: str = "tm") -> pd.Series:
    """Exclude positive pairs below the active threshold (zero disables it)."""
    missing = pd.Series(np.nan, index=frame.index)
    off = pd.to_numeric(frame.get(f"{metric}_off", missing), errors="coerce")
    on = pd.to_numeric(frame.get(f"{metric}_on", missing), errors="coerce")
    return (np.isfinite(off) & off.gt(0) & off.lt(MIN_RUNTIME_SECONDS)
            & np.isfinite(on) & on.gt(0) & on.lt(MIN_RUNTIME_SECONDS))


def runtime_filter_description() -> str:
    if MIN_RUNTIME_SECONDS == 0:
        return "No minimum runtime filter; retain all finite positive measured pairs, including both runtimes below 1 s"
    return "Exclude pairs with both runtimes < 1 s; retain pairs with at least one runtime >= 1 s"


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


def correctness_eligible(frame: pd.DataFrame) -> pd.Series:
    """Unchecked performance is explicit opt-out, never fabricated verification."""
    status = frame.get("correct", pd.Series("TRUE", index=frame.index)).astype(str).str.upper()
    mode = frame.get("correctness_check", pd.Series("", index=frame.index)).astype(str).str.lower()
    measured = frame.get("timing_status", pd.Series("", index=frame.index)).astype(str).str.lower().eq("measured")
    return status.eq("TRUE") | (status.eq("NOT-CHECKED") & mode.eq("disabled") & measured)


def timeout_mask(frame: pd.DataFrame) -> pd.Series:
    """Either engine's recorded timeout excludes the pair, even with finite times.

    Status fields are authoritative even when the human-readable note is absent.
    Recognize old capped exports too; never infer timeout from a runtime value.
    """
    result = pd.Series(False, index=frame.index)
    for name in ("note", "correct", "timing_status", "duckdb_status", "outeryan_status",
                 "duckdb_correctness_status", "outeryan_correctness_status",
                 "profile_status", "optimizer_profile_status", "runtime_treatment"):
        if name in frame:
            result |= frame[name].fillna("").astype(str).str.contains("timeout", case=False, regex=False)
    for name in ("duckdb_timeout_stage", "outeryan_timeout_stage"):
        if name in frame:
            stage = frame[name].fillna("").astype(str).str.strip().str.lower()
            result |= ~stage.isin(("", "-", "na", "n/a", "nan", "none", "null", "not-run"))
    return result


def timeout_substitution_mask(frame: pd.DataFrame) -> pd.Series:
    """Recognize an explicit reporting substitution, never infer one from NaN."""
    def column(name, default=""):
        return frame.get(name, pd.Series(default, index=frame.index))
    return (column("runtime_treatment").eq("duckdb_timeout_600s")
            & column("duckdb_status").eq("timeout")
            & column("outeryan_status").eq("measured")
            & pd.to_numeric(column("tm_off"), errors="coerce").eq(600)
            & pd.to_numeric(column("tm_on"), errors="coerce").gt(0)
            & np.isfinite(pd.to_numeric(column("tm_on"), errors="coerce"))
            & column("selected_plan").eq("OUTERYAN"))


def prepare_queries(frame: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Normalize reported outcomes without requiring the rounded speedup field."""
    if metric not in ("tm", "t1"):
        raise ValueError("metric must be tm or t1")
    if "run" in frame and frame["run"].nunique() > 1:
        raise ValueError("statistics require one logical run; do not mix thread configurations")
    if "timing_threads" in frame and frame["timing_threads"].nunique() > 1:
        raise ValueError("statistics require one timing thread count")
    identity_columns = query_identity_columns(frame)
    if frame.duplicated(identity_columns).any():
        raise ValueError("deduplicate final and attempts rows before computing statistics")
    columns = [column for column in (
        "experiment_group", "source_run", "source_csv", "corpus_version", "corpus_revision", "corpus_scope", "workload_category", "query_class",
        "sql_identity", "original_query", "original_workload_category", "original_sql_path",
        "query", "family", "topology", "workload_component", "source_component", "evaluation_role",
        "relation_count", "tree_shape", "join_graph_topology", "join_vector", "join_type_composition", "selectivity_level",
        "graph_filter_revision", "input_filter_placement", "input_filter_profiles_json",
        "aggregate_query", "aggregate_pushdown_applied", "selected_plan", "correct", "note", "timing_status",
        "timing_threads", "sql_path", "timeout_seconds", "correctness_check",
        "timing_protocol", "timing_samples", "timing_estimator", "warmup_runs_per_side",
        "duckdb_timeout_seconds", "outeryan_timeout_seconds", "duckdb_status", "outeryan_status",
        "duckdb_timeout_stage", "outeryan_timeout_stage", "duckdb_correctness_status", "outeryan_correctness_status",
        "runtime_treatment", "recorded_tm_off", "recorded_tm_on", "graph_dataset",
    ) if column in frame]
    detail = frame[columns].copy().reset_index(drop=True)
    detail["family"] = detail["family"].map(normalize_family)
    detail["selected_plan"] = detail.get("selected_plan", pd.Series("UNKNOWN", index=detail.index)).fillna(
        "UNKNOWN").astype(str).str.upper()
    correct = correctness_eligible(frame).reset_index(drop=True)
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
    timeout = timeout_mask(frame).reset_index(drop=True)
    fallback = timing_status.eq("fallback-skip") | notes.str.upper().eq("FALLBACK-SKIP")
    measured = correct & ~timeout & ~fallback & pair & np.isfinite(speedup) & speedup.gt(0)
    too_fast = measured & below_runtime_threshold(frame, metric).reset_index(drop=True)
    measured &= ~too_fast
    valid = measured
    detail["off_s"], detail["on_s"] = off, on
    detail["speedup"] = speedup.where(valid)
    detail["valid_timing"] = measured
    detail["valid_speedup"] = valid
    detail["speedup_source"] = np.where(fallback, "not-measured", np.where(measured, "measured", ""))
    # Exclusive reasons make coverage totals reconcile without double-counting.
    detail["exclusion_reason"] = np.select(
        [valid, timeout, too_fast, fallback, ~correct, ~pair],
        ["", "timeout", "both_runtimes_below_1s", "fallback_not_executed", "correctness_not_true", "missing_or_invalid_timing"],
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
        "timeout_substituted": int(valid["speedup_source"].eq("duckdb_timeout_600s").sum()),
        "unchecked_measured": int(measured.get("correct", pd.Series(dtype=str)).eq("NOT-CHECKED").sum()),
        "fallback_skips": int(rows["exclusion_reason"].eq("fallback_not_executed").sum()),
        "both_runtimes_below_1s": int(rows["exclusion_reason"].eq("both_runtimes_below_1s").sum()),
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
        "off_s": distribution(measured["off_s"]), "on_s": distribution(measured["on_s"]),
        "totals": {"off_s": total_off, "on_s": total_on,
                   "speedup": total_off / total_on if total_on is not None else None,
                   "saved_s": total_off - total_on if total_on is not None else None,
                   "time_reduction_fraction": 1 - total_on / total_off if total_off is not None else None},
    }


TIMEOUT_DIMENSIONS = (
    "family",
    "workload_category",
    "relation_count",
    "tree_shape",
    "join_graph_topology",
    "join_type_composition",
    "selectivity_level",
    "aggregate_query",
)


def build_timeout_statistics(detail: pd.DataFrame) -> dict:
    """Describe observed harness timeouts without inventing censored runtimes."""
    timeout_rows = detail.loc[detail["exclusion_reason"].eq("timeout")].copy()
    distributions = []
    for dimension in TIMEOUT_DIMENSIONS:
        if dimension not in detail:
            continue
        all_values = detail[dimension].copy()
        timeout_values = timeout_rows[dimension].copy()
        if dimension == "relation_count":
            all_values = pd.to_numeric(all_values, errors="coerce").map(
                lambda value: "Unspecified" if pd.isna(value) else (
                    str(int(value)) if float(value).is_integer() else str(value)
                )
            )
            timeout_values = pd.to_numeric(timeout_values, errors="coerce").map(
                lambda value: "Unspecified" if pd.isna(value) else (
                    str(int(value)) if float(value).is_integer() else str(value)
                )
            )
        else:
            all_values = all_values.map(lambda value: "Unspecified" if pd.isna(value) or str(value).strip() == "" else str(value))
            timeout_values = timeout_values.map(
                lambda value: "Unspecified" if pd.isna(value) or str(value).strip() == "" else str(value)
            )
        totals = all_values.value_counts(dropna=False)
        timed_out = timeout_values.value_counts(dropna=False)
        for value in sorted(totals.index, key=lambda item: str(item)):
            total = int(totals[value])
            count = int(timed_out.get(value, 0))
            distributions.append({
                "dimension": dimension,
                "value": str(value),
                "total_queries": total,
                "timeout_queries": count,
                "timeout_rate": count / total if total else None,
                "share_of_timeouts": count / len(timeout_rows) if len(timeout_rows) else None,
            })
    query_columns = [column for column in (
        "query", "family", "workload_category", "relation_count", "tree_shape",
        "join_graph_topology", "join_vector", "join_type_composition", "selectivity_level",
        "aggregate_query", "selected_plan", "timing_status", "note", "sql_path",
        "off_s", "on_s", "duckdb_timeout_seconds", "outeryan_timeout_seconds",
        "duckdb_status", "outeryan_status", "duckdb_timeout_stage", "outeryan_timeout_stage",
        "duckdb_correctness_status", "outeryan_correctness_status",
    ) if column in timeout_rows]
    selected_counts = timeout_rows["selected_plan"].value_counts().sort_index().to_dict()
    limits = sorted(pd.to_numeric(detail.get("timeout_seconds", pd.Series(dtype=float)),
                                  errors="coerce").dropna().unique().tolist())
    engine_limits = {side: sorted(pd.to_numeric(detail.get(f"{side}_timeout_seconds", pd.Series(dtype=float)),
                                              errors="coerce").dropna().unique().tolist())
                     for side in ("duckdb", "outeryan")}
    recorded_limits = sorted(set(limits + engine_limits["duckdb"] + engine_limits["outeryan"]))
    has_limit_columns = any(c in detail for c in ("timeout_seconds", "duckdb_timeout_seconds", "outeryan_timeout_seconds"))
    # Legacy records with no limit columns keep the historical default. Unknown
    # or asymmetric limits in modern records must not be fabricated as 600 s.
    limit = recorded_limits[0] if len(recorded_limits) == 1 else TIMEOUT_SECONDS if not has_limit_columns else None
    per_engine = {}
    for side in ("duckdb", "outeryan"):
        column = f"{side}_status"
        if column not in timeout_rows:
            continue  # Old logs do not reliably identify which side timed out.
        mask = timeout_rows[column].eq("timeout")
        stages = timeout_rows.loc[mask, f"{side}_timeout_stage"].value_counts().to_dict() if f"{side}_timeout_stage" in timeout_rows else {}
        per_engine[side] = {"timeout_queries": int(mask.sum()), "stages": {str(k): int(v) for k, v in stages.items()},
                            "family_counts": {str(k): int(v) for k, v in timeout_rows.loc[mask, "family"].value_counts().to_dict().items()}}
    return {
        "limit_seconds": limit,
        "limit_minutes": limit / 60 if limit is not None else None,
        "recorded_limits_seconds": recorded_limits,
        "engine_limits_seconds": engine_limits,
        "per_engine": per_engine,
        "limit_source": "recorded_csv" if has_limit_columns else "legacy_default",
        "total": len(timeout_rows),
        "input_total": len(detail),
        "rate": len(timeout_rows) / len(detail) if len(detail) else None,
        "selected_plan_counts": {str(key): int(value) for key, value in selected_counts.items()},
        "distribution": distributions,
        "queries": json.loads(timeout_rows[query_columns].to_json(orient="records", double_precision=15)),
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
        "query", "family", "topology", "selected_plan", "correct", "correctness_check", "timing_status", "note",
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
    correct = correctness_eligible(detail)
    not_timeout = ~timeout_mask(frame).reset_index(drop=True)
    finite = np.isfinite(detail["profile_wall_time_s"]) & detail["profile_wall_time_s"].gt(0)
    finite &= np.isfinite(detail["profile_cpu_time_s"]) & detail["profile_cpu_time_s"].gt(0)
    for _, column in PHASE_COMPONENTS:
        finite &= np.isfinite(detail[column]) & detail[column].ge(0)
    detail = detail.loc[selected & complete & correct & not_timeout & finite
                        & ~below_runtime_threshold(detail, metric)].copy()
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


def build_optimizer_statistics(frame: pd.DataFrame, metric: str = "tm") -> dict:
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

    frame = frame.loc[~below_runtime_threshold(frame, metric)]
    columns = [column for column in (
        "experiment_group", "corpus_version", "corpus_scope", "workload_category", "query_class",
        "query", "family", "selected_plan", "correct", "correctness_check", "timing_status", "note", "optimizer_profile_status",
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
    correct = correctness_eligible(detail)
    not_timeout = ~timeout_mask(frame).reset_index(drop=True)
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
        for dimension in ("tree_shape", "join_graph_topology", "join_type_composition", "selectivity_level"):
            if dimension in detail:
                group_specs.append((dimension, [dimension]))
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
                    **identity,
                    **summarize(group_rows),
                })
    source_info = []
    for source in sources or []:
        path = Path(source).resolve()
        source_info.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "rows": len(pd.read_csv(path)),
                            "kind": "attempts" if path.name.endswith(".attempts.csv") else "final"})
    return {
        "schema_version": 5,
        "run": (
            str(frame["run"].iloc[0]) if "run" in frame and len(frame)
            else str(frame["experiment_group"].iloc[0]) if "experiment_group" in frame and len(frame)
            else None
        ),
        "metric": metric, "timing_threads": sorted(frame["timing_threads"].dropna().astype(int).unique().tolist())
        if "timing_threads" in frame else [],
        "sources": source_info, "input_rows": sum(source["rows"] for source in source_info) if source_info else None,
        "unique_queries": len(detail),
        "valid_queries": int(detail["valid_speedup"].sum()),
        "headline": {"population": "measured_outeryan_selected", **summarize(
            detail.loc[detail["valid_speedup"] & detail["selected_plan"].eq("OUTERYAN")]
        )},
        "method": {
            "speedup": "Measured rows use OFF / ON from original unrounded timing pairs; values > 1 mean faster",
            "population": ("Performance-screened subset: historical exclusions plus both runtimes >1s and below the recorded timeout, and speed-up >=0.8; not an unbiased overall sample"
                           if "qualification_policy" in frame and frame["qualification_policy"].eq("performance_screened").all()
                           else "Historically screened candidates, before post-measurement qualification; report failures and exclusions"
                           if "corpus_revision" in frame and frame["corpus_revision"].eq("balanced-screened-20261002").all()
                           else "Original supplied experiment population"),
            "eligibility": "Only verified or explicitly NOT-CHECKED/disabled measured pairs with finite positive non-timeout OFF/ON times; failures and untimed fallback rows are excluded. " + runtime_filter_description(),
            "correctness": "NOT-CHECKED with correctness_check=disabled is performance-only evidence, not a correctness claim; failed or unspecified checks are excluded",
            "timing_protocols": frame[[c for c in ("timing_protocol", "timing_samples", "timing_estimator", "warmup_runs_per_side") if c in frame]].drop_duplicates().fillna("").to_dict("records"),
            "minimum_runtime": runtime_filter_description() + ". Apply the same query filter to phase and optimizer summaries; retain raw rows for coverage",
            "minimum_runtime_seconds": MIN_RUNTIME_SECONDS,
            "fallback": "timing_status=fallback-skip means no performance measurement occurred; correctness may still be verified; the original placeholder 1.0 is not used in statistics",
            "deduplication": "Unique execution-family/SQL identities across names and historical suites; latest observations win including failures; unresolved definitions remain separate",
            "strata": "Manifest tree_shape and join_graph_topology are distinct; topology is the legacy name-inferred display shape. Join-type composition counts I/L/R/F edges. Selectivity levels are nominal manifest targets, not measured cardinalities; unspecified metadata is not inferred from runtime",
            "geomean": "exp(mean(log(OFF / ON))), each eligible query weighted equally",
            "headline": "Geometric-mean speed-up and maximum in the performance overview use only valid measured queries with selected_plan=OUTERYAN",
            "total_speedup": "sum(OFF) / sum(ON) over measured timing pairs only; fallback skips have no fabricated runtime",
            "stddev_variance": "Sample statistics (ddof=1); unavailable for n < 2",
            "percentiles": "Linear interpolation; p50 is median",
            "excluded": "No timeout substitution, runtime imputation, speed-up trimming, or use of the representative display sample",
            "timeout": "Any recorded timeout on either engine, at any stage, excludes the query from valid pairs, performance statistics and plots. Status, stage and note fields are checked; legacy capped values are also excluded. No timeout-limit substitution is permitted. Limits are retained for diagnostics only",
            "uncertainty": "Descriptive query-level statistics, not confidence intervals over repeated runs",
        },
        "groups": groups,
        "timeouts": build_timeout_statistics(detail),
        "phase_profiles": build_phase_statistics(frame, metric),
        "optimizer_profiles": build_optimizer_statistics(frame, metric),
        "queries": json.loads(detail.to_json(orient="records", double_precision=15)),
    }


def number(value: float | None, digits: int = 4) -> str:
    """Format report cells as plain text, with no manuscript markup."""
    if value is None or not math.isfinite(float(value)):
        return "--"
    return f"{value:.{digits}f}"


def markdown_report(report: dict) -> str:

    lines = ["# Benchmark statistics", "", f"Run: `{report['run']}`. Metric: `{report['metric']}`. "
             f"Timing threads: {report['timing_threads'] or 'legacy / unspecified'}.", "",
             "## Definitions and coverage", ""]
    lines.extend(f"- {name}: {definition}." for name, definition in report["method"].items())
    headline = report["headline"]
    lines.extend(["", f"Valid measured queries: {report['valid_queries']}. "
                  f"OuterYan-selected: {headline['counts']['valid']}; "
                  f"geometric-mean speed-up: {number(headline['speedup']['geomean'])}×.",
                  f"Input records after reconciliation (before exclusions): {report['unique_queries']}.", ""])
    timeouts = report["timeouts"]
    lines.extend([
        f"## Timeout distribution ({timeouts['limit_minutes']}-minute limit)", "",
        f"Observed timeouts: {timeouts['total']} / {timeouts['input_total']} "
        f"({number(100 * timeouts['rate'])}%). Timeout runtimes are censored and are not replaced with the limit.",
        f"Selected-plan counts among timeouts: {timeouts['selected_plan_counts']}.", "",
        "| Dimension | Stratum | Timeout / total | Timeout rate (%) | Share of all timeouts (%) |",
        "|---|---|---:|---:|---:|",
    ])
    displayed_dimensions = {"family", "workload_category", "relation_count", "tree_shape", "selectivity_level", "aggregate_query"}
    for row in timeouts["distribution"]:
        if row["dimension"] not in displayed_dimensions or not row["timeout_queries"]:
            continue
        lines.append(
            f"| {row['dimension']} | {row['value']} | {row['timeout_queries']} / {row['total_queries']} | "
            f"{number(100 * row['timeout_rate'])} | {number(100 * row['share_of_timeouts'])} |"
        )
    lines.extend(["", "Complete timeout strata are in `timeout_summary.csv`; exact query names and metadata are in `timeout_queries.csv`.", ""])
    family_order = {name: index for index, name in enumerate(("all", "Graph", "TPC-H", "TPC-DS", "JOB"))}
    for subset in ("outeryan_selected", "all", "duckdb_selected"):
        rows = [row for row in report["groups"] if row["subset"] == subset and row["scope"] in ("overall", "benchmark")]
        rows.sort(key=lambda row: family_order[row["family"]])
        lines.extend([f"## {subset}", "", "### Speed-up distribution", "",
                      "| Benchmark | Speed-ups / total | Measured | Unexecuted excluded | Both <1s excluded | Min | Max | Geomean | Mean | Median | Sample SD | Total-time speed-up |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for row in rows:
            stats, counts = row["speedup"], row["counts"]
            values = [stats[key] for key in ("min", "max", "geomean", "mean", "median", "stddev")]
            lines.append(f"| {row['family']} | {counts['valid']} / {counts['total']} | "
                         f"{counts['measured']} | {counts['fallback_skips']} | {counts['both_runtimes_below_1s']} | " +
                         " | ".join(number(value) for value in values + [row["totals"]["speedup"]]) + " |")
        lines.extend(["", "### Percentiles and dispersion", "",
                      "| Benchmark | P05 | P10 | P25 | P75 | P90 | P95 | P99 | Variance | CV |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for row in rows:
            lines.append(f"| {row['family']} | " + " | ".join(number(row["speedup"][key]) for key in
                         ("p05", "p10", "p25", "p75", "p90", "p95", "p99", "variance", "cv")) + " |")
        lines.extend(["", "### Coverage and faster/slower counts", "",
                      "Measured faster/slower use exact OFF/ON; untimed fallback skips are excluded. "
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
        for dimension in ("tree_shape", "join_graph_topology", "join_type_composition", "selectivity_level"):
            strata = [row for row in report["groups"] if row["subset"] == subset and row["scope"] == dimension]
            if strata:
                lines.extend(["", f"### {dimension}", "",
                              "| Stratum | Valid / total | Measured | Geomean | Max |",
                              "|---|---:|---:|---:|---:|"])
                for row in strata:
                    counts = row["counts"]
                    lines.append(f"| {row[dimension]} | {counts['valid']} / {counts['total']} | "
                                 f"{counts['measured']} | {number(row['speedup']['geomean'])} | "
                                 f"{number(row['speedup']['max'])} |")
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
            "both_runtimes_below_1s": row["counts"]["both_runtimes_below_1s"],
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

    strata_rows = []
    for row in report["groups"]:
        if row["subset"] not in ("all", "outeryan_selected") or row["scope"] not in TIMEOUT_DIMENSIONS:
            continue
        value = row.get(row["scope"], "Unspecified")
        if pd.isna(value) or str(value).strip() == "":
            value = "Unspecified"
        strata_rows.append({
            "subset": row["subset"],
            "dimension": row["scope"],
            "value": value,
            "valid": row["counts"]["valid"],
            "total": row["counts"]["total"],
            "faster": row["counts"]["faster"],
            "slower": row["counts"]["slower"],
            "geomean": row["speedup"]["geomean"],
            "median": row["speedup"]["median"],
            "max": row["speedup"]["max"],
            "total_time_speedup": row["totals"]["speedup"],
        })
    strata_columns = [
        "subset", "dimension", "value", "valid", "total", "faster", "slower",
        "geomean", "median", "max", "total_time_speedup",
    ]
    pd.DataFrame(strata_rows, columns=strata_columns).to_csv(
        output_directory / "strata_statistics.csv", index=False
    )

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
    timeout_columns = [
        "dimension", "value", "total_queries", "timeout_queries", "timeout_rate", "share_of_timeouts",
    ]
    pd.DataFrame(report["timeouts"]["distribution"], columns=timeout_columns).to_csv(
        output_directory / "timeout_summary.csv", index=False
    )
    timeout_query_columns = [
        "query", "family", "workload_category", "relation_count", "tree_shape",
        "join_graph_topology", "join_vector", "join_type_composition", "selectivity_level",
        "aggregate_query", "selected_plan", "timing_status", "note", "sql_path",
        "off_s", "on_s", "duckdb_timeout_seconds", "outeryan_timeout_seconds",
        "duckdb_status", "outeryan_status", "duckdb_timeout_stage", "outeryan_timeout_stage",
        "duckdb_correctness_status", "outeryan_correctness_status",
    ]
    pd.DataFrame(report["timeouts"]["queries"]).reindex(columns=timeout_query_columns).to_csv(
        output_directory / "timeout_queries.csv", index=False
    )
    return report



# ---- CSV reconciliation and figure rendering --------------------------------

# Matplotlib is needed only for rendering, never for harness statistics.
plt = PdfPages = HandlerTuple = Line2D = Patch = None


def _load_plotting() -> None:
    global plt, PdfPages, HandlerTuple, Line2D, Patch
    if plt is not None:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.legend_handler import HandlerTuple
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    plt.rcParams.update(ACADEMIC_STYLE)


C_T1 = "#4C72B0"
C_TM = "#DD8452"
PHASE_RUNTIME_DUCKDB_COLOR = "#A78BFA"
PHASE_RUNTIME_OUTERYAN_COLOR = "#FB7185"
PHASE_RUNTIME_EDGE_COLOR = "#5C5470"
FAMILY_ORDER = ["graph", "TPC-H", "TPC-DS", "JOB"]
FAMILY_COLORS = {
    "graph": "#7A7A7A",
    "TPC-H": "#E64B35",
    "TPC-DS": "#315EFB",
    "JOB": "#00A087",
}
REPRESENTATIVE_QUERIES_PER_FAMILY = 15
TOPOLOGY_ORDER = ["left-deep", "right-deep", "bushy", "star", "aggregate", "industry"]
CLASS_ORDER = ["join", "graph", "derived", "industry", "aggregation", "selectivity stress", "JOB regression", "custom", "legacy"]
QUERY_TYPE_CODES = {"join": "Q", "graph": "G", "control": "G", "aggregate": "A"}
FAMILY_CODES = {"graph": "G", "TPC-H": "H", "TPC-DS": "D", "JOB": "J"}


def figure_family_label(family: str) -> str:
    """Keep source/statistics family keys stable while naming the plotted workload."""
    return "SGPB" if family.lower() == "graph" else family


TOPOLOGY_CODES = {
    "left-deep": "LD",
    "right-deep": "RD",
    "bushy": "B",
    "star": "S",
    "aggregate": "A",
    "industry": "I",
    "other": "O",
}
PHASE_SAMPLE_PER_FAMILY = 20
PHASE_GROUP_GAP = 0.62
QUERY_POINT_SIZE = 28
QUERY_POINT_ALPHA = 0.52
QUERY_CODE_KEY = (
    "G=SGPB, H=TPC-H, D=TPC-DS, J=JOB; LD=left-deep, RD=right-deep, "
    "B=bushy, S=star, I=industry, O=other; type prefix: Q=join, G=graph, A=aggregation"
)
RUNTIME_SERIES = [
    ("Single-thread: DuckDB (OFF)", "t1_off", "#A4BEDF"),
    ("Single-thread: OuterYan (ON)", "t1_on", "#6B9AC7"),
    ("Multi-thread: DuckDB (OFF)", "tm_off", "#EFC69E"),
    ("Multi-thread: OuterYan (ON)", "tm_on", "#E59C6D"),
]
PHASES = [
    ("Round 1", "profile_round1_operator_s", "profile_round1_ratio", "#3B6FB6"),
    ("Round 2", "profile_round2_operator_s", "profile_round2_ratio", "#5AAE61"),
    ("Round 3", "profile_round3_operator_s", "profile_round3_ratio", "#E08245"),
    ("Other OP", "profile_other_elapsed_s", "profile_other_ratio", "#A0A0A0"),
]
PROFILE_CPU_TOTAL_LABEL = "Profile CPU total"

ACADEMIC_STYLE = {
    "font.family": "serif",
    "font.serif": ["DejaVu Serif"],
    "mathtext.fontset": "dejavuserif",
    "axes.edgecolor": "#303030",
    "axes.linewidth": 0.8,
    "axes.labelsize": 10,
    "axes.titlesize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "savefig.facecolor": "white",
}

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUTS = ["results/experiment_onoff_*.csv"]
DEFAULT_OUTPUT_ROOT = SCRIPT_DIR / "results" / "plots"
STANDALONE_PNG_DPI = 300


def benchmark_provenance() -> pd.DataFrame:
    """Resolve current and archived query definitions without mixing revisions."""
    root = SCRIPT_DIR / "outerjoin_benchmark"
    manifests = list(historical_manifests(root)) + [(None, root / "benchmark" / "manifest.csv")]
    frames = []
    for category, path in manifests:
        if category == "v2_job_regressions":
            continue
        if not path.exists():
            continue
        manifest = pd.read_csv(path)
        if "query_id" not in manifest:
            continue
        columns = [column for column in (
            "query_id", "source_component", "evaluation_role", "tree_shape", "topology",
            "join_vector", "selectivity_tier", "target_fraction",
            "filter_design_revision", "target_min_fraction", "target_max_fraction",
            "target_min_inclusive", "target_max_inclusive",
            "calibration_fraction", "selectivity_profile", "selectivity_scope",
            "graph_filter_revision", "input_filter_placement", "input_filter_profiles_json",
        ) if column in manifest]
        part = manifest[columns].copy().rename(columns={"topology": "join_graph_topology"})
        if category == "v3_selectivity_stress":
            part["source_component"] = "selectivity_ablation"
            part["evaluation_role"] = "selectivity_ablation"
        part["workload_category"] = manifest["query_class"] if category is None else category
        frames.append(part)
    if not frames:
        return pd.DataFrame(
            columns=["query_id", "source_component", "evaluation_role", "workload_component"]
        )
    provenance = pd.concat(frames, ignore_index=True).drop_duplicates(["workload_category", "query_id"], keep="last")
    provenance["workload_component"] = provenance["source_component"].map(
        {"core": "structural", "industry_inspired": "evaluation",
         "v1_active_evaluation": "evaluation", "evaluation": "evaluation", "selectivity_ablation": "selectivity_ablation",
         "historical_recovery": "historical_recovery"}
    ).fillna("unknown")
    for column in ("tree_shape", "join_graph_topology", "join_vector", "selectivity_tier"):
        provenance[column] = provenance.get(column, pd.Series(dtype=str)).fillna("unspecified")
    provenance["tree_shape"] = provenance["tree_shape"].str.replace("_", "-", regex=False)
    provenance["join_graph_topology"] = provenance["join_graph_topology"].replace({"branched": "branch"})
    provenance["join_type_composition"] = provenance["join_vector"].map(
        lambda value: "-".join(f"{kind}{value.count(kind)}" for kind in "ILRF")
        if value and set(value) <= set("ILRF") else "unspecified"
    )
    fraction = pd.to_numeric(provenance.get("target_fraction", pd.Series(dtype=float)), errors="coerce")
    provenance["selectivity_level"] = fraction.map(lambda value: f"{100 * value:g}%" if pd.notna(value) else "unspecified")
    if "filter_design_revision" in provenance:
        semantic = (provenance["filter_design_revision"].notna()
                    & provenance["target_min_fraction"].notna() & provenance["target_max_fraction"].notna())
        for index in provenance.index[semantic]:
            row = provenance.loc[index]
            left = "[" if row["target_min_inclusive"] in (True, "true") else "("
            right = "]" if row["target_max_inclusive"] in (True, "true") else ")"
            provenance.at[index, "selectivity_level"] = (
                f"{left}{100 * row['target_min_fraction']:g}%, {100 * row['target_max_fraction']:g}%{right}")
    historical = provenance["evaluation_role"].eq("historical_slow_baseline_case")
    provenance.loc[historical, "selectivity_level"] = "Legacy modulo (unverified)"
    return provenance


def gmean(values: pd.Series | np.ndarray) -> float:
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data) & (data > 0)]
    return float(np.exp(np.mean(np.log(data)))) if data.size else np.nan


def strip_provenance_prefix(query: str) -> str:
    return re.sub(
        r"^(?:derived|industry|industrywin|legacywin|custom|stress|regression|aggregate)__(?:sem__)?",
        "",
        str(query),
        flags=re.IGNORECASE,
    )


def class_from_query(query: str) -> str | None:
    prefix = str(query).split("__", 1)[0].lower() if "__" in str(query) else ""
    return {
        "derived": "derived",
        "join": "join",
        "graph": "graph",
        "control": "graph",  # Historical result compatibility.
        "industry": "industry",
        # Compatibility for result files generated before the two-prefix merge.
        "industrywin": "industry",
        "legacywin": "derived",
        "custom": "custom",
        "stress": "selectivity stress",
        "aggregate": "aggregation",
        "regression": "JOB regression",
    }.get(prefix)


def family_from_query(query: str) -> str:
    parts = str(query).split("__")
    if len(parts) > 2 and parts[0] in ("join", "graph", "control", "aggregate"):
        return {"tpch": "TPC-H", "tpcds": "TPC-DS", "job": "JOB", "graph": "graph"}.get(parts[1], "graph")
    query = strip_provenance_prefix(query).lower()
    if query.startswith(("oy_th", "ojb_tpch", "ojb_sqlstorm_tpch")):
        return "TPC-H"
    if query.startswith(("oy_ds", "ojb_tpcds", "ojb_sqlstorm_tpcds")):
        return "TPC-DS"
    if query.startswith(("oy_jb", "ojb_job", "ojb_sqlstorm_job")):
        return "JOB"
    return "graph"


def topology_from_query(query: str) -> str:
    parts = str(query).split("__")
    if len(parts) > 2 and parts[0] in ("join", "graph", "control", "aggregate"):
        query = parts[2]
    query = strip_provenance_prefix(query).lower()
    query = re.sub(r"_(?:grouped_(?:sum|min|max)|global_count|distinct)$", "", query)
    selectivity_suffix = (
        r"(?:_(?:sel(?:001|01|05|_(?:low|medium|high))|"
        r"stress(?:0025|005|02|10|20|50|80|_(?:low|medium|high))))?$"
    )
    if re.search(r"_(?:ldmx|ldu[lrfi]|alt)" + selectivity_suffix, query):
        return "left-deep"
    if re.search(r"_(?:rdmx|rdax|rdu[lrfi])" + selectivity_suffix, query):
        return "right-deep"
    if re.search(r"_(?:bmx|bdmx)" + selectivity_suffix, query):
        return "bushy"
    if "_real_" in query:
        return "industry"
    core = re.sub(r"^oy_(?:th|ds|jb)_(?:th|ds|jb|real)_", "", query)
    if core.startswith("agg"):
        return "aggregate"
    if "_rd_" in core or re.match(r"(?:rd|rdeep)(?:\d|_)", core):
        return "right-deep"
    if core.startswith("line"):
        return "left-deep"
    if core.startswith(("bushy", "branch")):
        return "bushy"
    if core.startswith("star"):
        return "star"
    return "other"


def relation_count_from_name(query: str) -> float:
    query = strip_provenance_prefix(query)
    for pattern in (
        r"(?:^|_)N(\d+)(?=_|$)",
        r"(?:^|_)(?:line|bushyBal|bushy|rdeep|rd|branch|star)(\d+)[a-z]?(?=_|$)",
    ):
        match = re.search(pattern, query)
        if match:
            return float(match.group(1))
    if re.search(r"_(?:th|ds|jb)_agg\d+$", query):
        return 3.0
    return np.nan


def result_source(path: str) -> tuple[str, str, str]:
    """Return logical run timestamp, final/attempt source, and corpus label."""
    stem = re.sub(r"\.csv$", "", os.path.basename(path), flags=re.IGNORECASE)
    source_kind = "attempts" if stem.lower().endswith(".attempts") else "final"
    if source_kind == "attempts":
        stem = stem[: -len(".attempts")]
    stem = re.sub(r"_(?:v[123](?:_selectivity_stress)?|all)$", "", stem)
    stem = re.sub(r"^experiment_onoff_", "", stem)
    match = re.search(r"(?:^|_)(\d{8}_\d{6})(_t[1-9][0-9]*)?$", stem)
    if not match:
        return stem, source_kind, "custom"
    run = match.group(1) + (match.group(2) or "")
    label = stem[: match.start()].rstrip("_") or "legacy"
    return run, source_kind, label


def query_identity_columns(frame: pd.DataFrame) -> list[str]:
    if "sql_identity" in frame:
        return ["sql_identity"]
    return [column for column in ("workload_category", "family", "query") if column in frame]


def source_query_class(label: str) -> str:
    return {
        "core": "derived",
        "industry_inspired": "industry",
        "supplemental": "derived",
        "custom": "custom",
        "legacy": "legacy",
        "benchmark": "derived",
    }.get(label, "custom")


def enrich(frame: pd.DataFrame, run: str) -> pd.DataFrame:
    frame = frame.copy()
    frame["run"] = run
    numeric = [
        "t1_off", "t1_on", "t1_speedup", "tm_off", "tm_on", "tm_speedup", "rows",
        "relation_count", "timing_threads", "profile_threads", "profile_wall_time_s",
        "profile_total_time_s", "profile_cpu_time_s",
        *(seconds for _, seconds, _, _ in PHASES),
        *(ratio for _, _, ratio, _ in PHASES),
    ]
    for column in numeric:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    # Before September 2026 the misleading profile_total_time_s name held root
    # wall latency. Preserve that input contract while normalizing new data to
    # the explicit wall/aggregate-CPU schema.
    if "profile_wall_time_s" not in frame and "profile_total_time_s" in frame:
        frame["profile_wall_time_s"] = frame["profile_total_time_s"]
    if "profile_cpu_time_s" not in frame and "profile_total_time_s" in frame:
        frame["profile_cpu_time_s"] = frame["profile_total_time_s"]

    inferred_family = frame["query"].map(family_from_query)
    if "family" in frame:
        reported = frame["family"].fillna("").astype(str).str.strip().str.lower().map(
            {"graph": "graph", "tpch": "TPC-H", "tpc-h": "TPC-H",
             "tpcds": "TPC-DS", "tpc-ds": "TPC-DS", "job": "JOB"}
        )
        frame["family"] = reported.fillna(inferred_family)
    else:
        frame["family"] = inferred_family

    inferred_class = frame["query"].map(class_from_query)
    source_class = frame.get(
        "__plot_query_class", pd.Series("custom", index=frame.index, dtype="object")
    )
    frame["query_class"] = inferred_class.where(inferred_class.notna(), source_class)
    frame["topology"] = frame["query"].map(topology_from_query)

    fallback_relations = frame["query"].map(relation_count_from_name)
    sql_relations = pd.Series(np.nan, index=frame.index, dtype="float64")
    if "sql_path" in frame:
        corpus_root = SCRIPT_DIR / "outerjoin_benchmark"

        def relation_count_from_sql_path(relative_path: object, category: str) -> float:
            if not isinstance(relative_path, str) or not relative_path:
                return np.nan
            path = Path(relative_path)
            if path.is_absolute() or ".." in path.parts:
                return np.nan
            try:
                sql = resolve_sql_path(category, path, corpus_root).read_text(encoding="utf-8")
            except (OSError, ValueError):
                return np.nan
            count = count_base_relations(sql)
            return float(count) if count > 0 else np.nan

        categories = frame.get("workload_category", pd.Series("v1", index=frame.index))
        sql_relations = pd.Series([relation_count_from_sql_path(path, category)
                                  for path, category in zip(frame["sql_path"], categories)], index=frame.index)
    if "relation_count" in frame:
        frame["csv_relation_count"] = frame["relation_count"]
        valid = frame["relation_count"].where(
            frame["relation_count"].gt(0)
            & frame["relation_count"].eq(np.floor(frame["relation_count"]))
        )
        frame["relation_count"] = sql_relations.fillna(valid).fillna(fallback_relations)
    else:
        frame["relation_count"] = sql_relations.fillna(fallback_relations)

    frame["display_query"] = frame["query"].astype(str)
    provenance = benchmark_provenance()
    versioned = "workload_category" in provenance and "workload_category" in frame
    if versioned:
        provenance = provenance.set_index(["workload_category", "query_id"])
        lookup = pd.MultiIndex.from_arrays([frame["workload_category"], frame["query"]])
    else:
        provenance = provenance.drop_duplicates("query_id", keep="last").set_index("query_id")
        lookup = frame["query"]
    for column in ("source_component", "evaluation_role", "workload_component", "tree_shape",
                   "join_graph_topology", "join_vector", "join_type_composition", "selectivity_tier",
                   "target_fraction", "selectivity_level", "graph_filter_revision",
                   "input_filter_placement", "input_filter_profiles_json"):
        if column not in frame and column in provenance:
            frame[column] = provenance[column].reindex(lookup).to_numpy()
    return frame


def deduplicate_sql_results(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest complete record (including failures), never the fastest run."""
    frame = frame.copy()
    root = SCRIPT_DIR / "outerjoin_benchmark"
    manifest = root / "benchmark" / "manifest.csv"
    canonical = {row["sql_fingerprint"]: row for row in read_manifest(manifest)
                 if row.get("sql_fingerprint")} if manifest.is_file() else {}
    cache = {}
    records = []
    for _, source in frame.iterrows():
        row = source.to_dict()
        category = str(row.get("workload_category", "legacy"))
        family = str(row.get("family", family_from_query(row["query"])))
        relative = row.get("sql_path")
        original_category = row.get("original_workload_category")
        original_path = row.get("original_sql_path")
        source_category = original_category if isinstance(original_category, str) and original_category else category
        source_path = original_path if isinstance(original_path, str) and original_path else relative
        fingerprint = None
        if isinstance(source_path, str) and source_path:
            lookup = (source_category, source_path, family)
            if lookup not in cache:
                try:
                    path = resolve_sql_path(source_category, source_path, root)
                    cache[lookup] = sql_fingerprint(path.read_text(encoding="utf-8"), family)
                except (OSError, ValueError):
                    cache[lookup] = None
            fingerprint = cache[lookup]
        for key, value in (("original_query", row["query"]),
                           ("original_workload_category", category), ("original_sql_path", relative)):
            if not isinstance(row.get(key), str) or not row[key]:
                row[key] = value
        row["sql_identity"] = fingerprint or "unresolved:" + json.dumps([source_category, family, row["original_query"]])
        metadata = canonical.get(fingerprint)
        if metadata:
            row.update(query=metadata["query_id"], display_query=metadata["query_id"],
                       sql_path=metadata["path"], workload_category=metadata["query_class"],
                       selectivity_stress=metadata["selectivity_stress"] == "true")
            for name in ("source_component", "evaluation_role", "join_vector", "selectivity_tier"):
                row[name] = metadata[name]
            row["tree_shape"] = metadata["tree_shape"].replace("_", "-")
            row["topology"] = row["tree_shape"]
            row["join_graph_topology"] = metadata["topology"]
            row["workload_component"] = (
                "historical_recovery" if metadata.get("source_component") == "historical_recovery" else
                "evaluation" if metadata["query_class"] == "graph"
                or metadata.get("evaluation_role") == "historical_slow_baseline_case" else "structural")
            row["query_class"] = class_from_query(metadata["query_id"])
        else:
            category = "graph" if category == "control" else category
            kind = (category if category in ("join", "graph", "aggregate", "custom") else
                    "aggregate" if category == "v3_aggregation" or str(row["query"]).startswith("aggregate__")
                    else "graph" if row.get("workload_component") == "evaluation" else "join")
            row["workload_category"] = kind
            row["selectivity_stress"] = source_category == "v3_selectivity_stress"
            if fingerprint:
                stem = strip_provenance_prefix(str(row["original_query"])).lower()
                stem = re.sub(r"_v\d+(?=_|$)", "", stem)
                family_code = {"tpc-h": "tpch", "tpc-ds": "tpcds"}.get(family.lower(), family.lower())
                row["query"] = f"{kind}__{family_code}__{stem}__{fingerprint[:10]}"
                row["display_query"] = row["query"]
                row["query_class"] = "aggregation" if kind == "aggregate" else kind
        records.append(row)
    if not records:
        return frame
    result = pd.DataFrame(records)
    # Inputs retain source time/priority ordering. SQL contents, not names or
    # measured speed-ups, determine equivalence and the surviving observation.
    result = result.drop_duplicates("sql_identity", keep="last").reset_index(drop=True)
    return result


def load(paths: list[str], group_by: str = "run", date: str | None = None) -> pd.DataFrame:
    if group_by not in ("run", "date"):
        raise ValueError("group_by must be run or date")
    grouped: dict[str, list[pd.DataFrame]] = {}
    for source_order, path in enumerate(sorted(dict.fromkeys(paths))):
        try:
            raw = pd.read_csv(path)
        except Exception as exc:
            print(f"  ! skip {path}: {exc}", file=sys.stderr)
            continue
        if raw.empty or "query" not in raw:
            print(f"  ! skip {path}: no query rows", file=sys.stderr)
            continue
        run, source_kind, label = result_source(path)
        raw = raw.copy()
        if "experiment_group" in raw:
            experiment_groups = raw["experiment_group"].dropna().astype(str).unique()
            if len(experiment_groups) > 1:
                raise ValueError(f"Multiple experiment groups in {path}")
            if len(experiment_groups) == 1 and experiment_groups[0]:
                thread_suffix = re.search(r"_t[1-9][0-9]*$", run)
                run = experiment_groups[0] + (thread_suffix.group() if thread_suffix and not re.search(r"_t\d+$", experiment_groups[0]) else "")
        if "timing_threads" in raw:
            threads = pd.to_numeric(raw["timing_threads"], errors="coerce").dropna().unique()
            if len(threads) > 1:
                raise ValueError(f"Multiple timing thread counts in {path}")
            if len(threads) == 1:
                if not np.isfinite(threads[0]) or threads[0] <= 0 or threads[0] != int(threads[0]):
                    raise ValueError(f"Invalid timing thread count in {path}")
                suffix = f"_t{int(threads[0])}"
                existing = re.search(r"_t\d+$", run)
                if existing and existing.group() != suffix:
                    raise ValueError(f"Filename and CSV thread counts disagree: {path}")
                run = re.sub(r"_t\d+$", "", run) + suffix
        day = re.match(r"(\d{8})(?:_|$)", run)
        if date and (day is None or day.group(1) != date):
            continue
        version = re.search(r"_(v[123])(_selectivity_stress)?(?:\.attempts)?\.csv$", str(path))
        category = "legacy"
        if version:
            category = "v3_selectivity_stress" if version.group(2) else "v3_aggregation" if version.group(1) == "v3" else version.group(1)
        if "workload_category" not in raw:
            raw["workload_category"] = category
        else:
            raw["workload_category"] = raw["workload_category"].fillna(category).replace("", category)
        raw["source_run"] = run
        raw["source_csv"] = str(Path(path).resolve())
        if group_by == "date" and day:
            suffix = re.search(r"_t\d+$", run)
            run = day.group(1) + (suffix.group() if suffix else "")
        raw["__plot_source_priority"] = 0 if source_kind == "attempts" else 1
        raw["__plot_component_priority"] = 0 if str(path).endswith("_all.csv") else 1
        raw["__plot_source_order"] = source_order
        raw["__plot_row_order"] = np.arange(len(raw))
        raw["__plot_query_class"] = source_query_class(label)
        grouped.setdefault(run, []).append(raw)
        print(
            f"  loaded {path} ({len(raw)} rows; run={run}; component={label}; source={source_kind})"
        )
    if not grouped:
        raise SystemExit("No usable CSV files.")

    frames: list[pd.DataFrame] = []
    order_columns = ["source_run", "__plot_source_priority", "__plot_component_priority", "__plot_source_order", "__plot_row_order"]
    for run, sources in grouped.items():
        combined = pd.concat(sources, ignore_index=True, sort=False)
        reported_family = combined.get(
            "family", pd.Series("", index=combined.index, dtype="object")
        ).fillna("").astype(str).str.strip().str.lower()
        merge_family = reported_family.where(
            reported_family.ne(""), combined["query"].map(family_from_query).str.lower()
        ).replace({"tpch": "tpc-h", "tpcds": "tpc-ds"})
        combined["__plot_merge_family"] = merge_family
        combined = combined.sort_values(order_columns, kind="stable")
        keys = ["__plot_merge_family", "query"]
        if "workload_category" in combined:
            keys.insert(0, "workload_category")
        duplicate_count = int(combined.duplicated(keys, keep="last").sum())
        merged = combined.drop_duplicates(keys, keep="last")
        merged = merged.drop(columns=[column for column in order_columns if column != "source_run"] + ["__plot_merge_family"])
        merged = deduplicate_sql_results(enrich(merged, run))
        duplicate_count = len(combined) - len(merged)
        frames.append(merged)
        print(
            f"  unified run {run}: {len(combined)} component rows -> "
            f"{len(merged)} benchmark queries ({duplicate_count} duplicates removed)"
        )
    return pd.concat(frames, ignore_index=True)


def timed(frame: pd.DataFrame, metric: str = "tm") -> pd.DataFrame:
    if "run" in frame and frame["run"].nunique() > 1:
        return pd.concat([timed(group, metric) for _, group in frame.groupby("run", sort=False)]).sort_index()
    detail = prepare_queries(frame, metric)
    selected = detail["valid_timing"] & detail["selected_plan"].eq("OUTERYAN")
    result = frame.loc[selected.to_numpy()].copy()
    result[f"{metric}_speedup"] = detail.loc[selected, "speedup"].to_numpy()
    return result


def grouped_box(ax: plt.Axes, frame: pd.DataFrame, column: str, order: list[str], title: str) -> None:
    _load_plotting()
    order = [value for value in order if value in set(frame[column].dropna())]
    if not order:
        ax.set_visible(False)
        return
    width = 0.38
    rng = np.random.default_rng(0)
    metrics = [
        (metric, color) for metric, color in (("t1_speedup", C_T1), ("tm_speedup", C_TM))
        if metric in frame and frame[metric].notna().any()
    ]
    for series_index, (metric, color) in enumerate(metrics):
        data = [frame.loc[frame[column].eq(value), metric].dropna().to_numpy() for value in order]
        positions = [index + (series_index - (len(metrics) - 1) / 2.0) * width for index in range(len(order))]
        boxes = ax.boxplot(
            data, positions=positions, widths=width * 0.9, patch_artist=True,
            showfliers=False,
            medianprops={"linewidth": 0},
            whiskerprops={"color": color, "linewidth": 0.8, "alpha": 0.65},
            capprops={"color": color, "linewidth": 0.8, "alpha": 0.65},
        )
        for box in boxes["boxes"]:
            box.set(facecolor=color, edgecolor=color, linewidth=0.8, alpha=0.62)
        for position, values in zip(positions, data):
            values = values[np.isfinite(values) & (values > 0)]
            if not values.size:
                continue
            ax.scatter(
                rng.normal(position, 0.025, len(values)), values, s=10, color=color,
                edgecolor="black", linewidth=0.15, alpha=0.48, zorder=3
            )
            mean = gmean(values)
            ax.scatter(position, mean, marker="D", s=18, color="white", edgecolor="black", zorder=5)
            ax.annotate(f"{mean:.2f}", (position, mean), xytext=(0, 7),
                        textcoords="offset points", ha="center", fontsize=6)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(
        [f"{value}\n(n={int(frame[column].eq(value).sum())})" for value in order], fontsize=8
    )
    ax.axhline(1.0, color="grey", linestyle="--", linewidth=1)
    ax.set_yscale("log")
    ax.set_ylabel("speed-up (×; >1 = faster)")
    ax.set_title(title)
    ax.legend(
        handles=[Patch(facecolor=color, edgecolor="none", alpha=0.62, label=metric[:2].upper())
                 for metric, color in metrics], fontsize=8
    )


def save_page(pdf: PdfPages, figure: plt.Figure) -> None:
    _load_plotting()
    pdf.savefig(figure, bbox_inches="tight")
    plt.close(figure)


class PngPage:
    """One-page sink with the PdfPages.savefig surface used by page renderers."""

    def __init__(self, path: Path, dpi: int = STANDALONE_PNG_DPI):
        self.path = path
        self.dpi = dpi

    def savefig(self, figure: plt.Figure, bbox_inches: str = "tight") -> None:
        figure.savefig(self.path, dpi=self.dpi, bbox_inches=bbox_inches)


def write_figure_pair(output_directory: Path, stem: str, draw) -> Path:
    """Render one vector PDF and one 300-dpi PNG from the same plotting function."""
    _load_plotting()
    pdf_path = output_directory / f"{stem}.pdf"
    with PdfPages(pdf_path) as pdf:
        draw(pdf)
    png_path = output_directory / f"{stem}.png"
    draw(PngPage(png_path))
    print(f"  wrote standalone figure: {pdf_path}")
    print(f"  wrote standalone figure: {png_path}")
    return pdf_path


def tighten_mosaic(figure: plt.Figure, rect: tuple[float, float, float, float]) -> None:
    """Apply tight layout while tolerating the intentional row-spanning JOB axis."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="This figure includes Axes that are not compatible with tight_layout",
        )
        figure.tight_layout(rect=rect)


def page_summary(pdf: PdfPages, frame: pd.DataFrame, run: str) -> None:
    _load_plotting()
    figure, axes = plt.subplots(1, 3, figsize=(17, 5.4))
    grouped_box(axes[0], frame, "family", FAMILY_ORDER, "Benchmark")
    grouped_box(axes[1], frame, "query_class", CLASS_ORDER, "Query Category")
    reorder = frame.get("reorder", pd.Series("", index=frame.index)).astype(str).replace(
        {"1": "Yes", "0": "No"}
    )
    summary = frame.copy()
    summary["reorder_label"] = reorder
    grouped_box(axes[2], summary, "reorder_label", ["Yes", "No"], "Join Order")
    figure.suptitle("OuterYan benchmark speed-up summary", fontsize=14)
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    save_page(pdf, figure)


def page_shape_relations(pdf: PdfPages, frame: pd.DataFrame, run: str) -> None:
    _load_plotting()
    figure, axes = plt.subplots(1, 2, figsize=(14, 5.4))
    shape_rows = frame.loc[frame["topology"].isin(TOPOLOGY_ORDER)].copy()
    grouped_box(axes[0], shape_rows, "topology", TOPOLOGY_ORDER, "Speed-up by query shape")
    relation_rows = frame.loc[frame["relation_count"].notna()].copy()
    relation_rows["relation_label"] = relation_rows["relation_count"].astype("Int64").astype(str)
    relation_order = sorted(relation_rows["relation_label"].unique(), key=int)
    grouped_box(
        axes[1], relation_rows, "relation_label", relation_order, "Speed-up by relation count"
    )
    figure.suptitle("Shape and scale — unified benchmark", fontsize=14)
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    save_page(pdf, figure)


def benchmark_mosaic(
    frame: pd.DataFrame, row_inches: float, minimum_height: float
) -> tuple[plt.Figure, dict[str, plt.Axes]]:
    """Lay out small families on the left and the larger JOB family on the right."""
    _load_plotting()
    counts = frame["family"].value_counts().to_dict()
    left_families = [
        family for family in ("graph", "TPC-H", "TPC-DS") if counts.get(family, 0) > 0
    ]
    has_job = counts.get("JOB", 0) > 0
    left_units = sum(max(counts[family], 3) for family in left_families)
    row_units = max(left_units, counts.get("JOB", 0), 1)
    height = min(18.0, max(minimum_height, 2.6 + row_inches * row_units))
    figure = plt.figure(figsize=(22.0 if has_job and left_families else 12.0, height))

    if has_job and left_families:
        height_ratios = [max(counts[family], 3) for family in left_families]
        grid = figure.add_gridspec(
            len(left_families), 2, width_ratios=[1.0, 1.15],
            height_ratios=height_ratios, hspace=0.48, wspace=0.58
        )
        axes = {
            family: figure.add_subplot(grid[index, 0])
            for index, family in enumerate(left_families)
        }
        axes["JOB"] = figure.add_subplot(grid[:, 1])
        return figure, axes

    families = left_families + (["JOB"] if has_job else [])
    grid = figure.add_gridspec(
        max(len(families), 1), 1,
        height_ratios=[max(counts[family], 3) for family in families] or None,
        hspace=0.48,
    )
    axes = {
        family: figure.add_subplot(grid[index, 0])
        for index, family in enumerate(families)
    }
    return figure, axes


def add_short_query_labels(frame: pd.DataFrame) -> pd.DataFrame:
    """Label by query type, execution family and tree shape; never suite version."""
    labeled = frame.copy()
    labeled["_family_code"] = labeled["family"].map(FAMILY_CODES).fillna("X")
    labeled["_shape_code"] = labeled["topology"].map(TOPOLOGY_CODES).fillna("O")
    kinds = labeled.get("workload_category", pd.Series("join", index=labeled.index))
    kinds = kinds.replace({"v1": "join", "v2": "join", "v3_aggregation": "aggregate",
                           "v3_selectivity_stress": "join"})
    labeled["_type_code"] = kinds.map(QUERY_TYPE_CODES).fillna("Q")
    identity = query_identity_columns(labeled)
    stable = labeled.sort_values(["family", "topology"] + [key for key in identity if key != "family"], kind="stable")
    stable["_shape_index"] = stable.groupby(["family", "_shape_code", "_type_code"], sort=False).cumcount() + 1
    labeled["_shape_index"] = stable["_shape_index"].reindex(labeled.index)
    labeled["short_query"] = [
        f"{kind}-{family}-{shape}-{index:02d}"
        for kind, family, shape, index in zip(labeled["_type_code"], labeled["_family_code"],
                                             labeled["_shape_code"], labeled["_shape_index"])
    ]
    return labeled


def sample_phase_queries(frame: pd.DataFrame, limit: int = PHASE_SAMPLE_PER_FAMILY) -> pd.DataFrame:
    """Select deterministic, evenly spaced rows from each family and runtime range."""
    sampled: list[pd.DataFrame] = []
    family_sizes = frame["family"].value_counts().to_dict()
    for family in FAMILY_ORDER:
        family_rows = frame.loc[frame["family"].eq(family)].sort_values(
            ["topology", "profile_cpu_time_s", "query"], kind="stable"
        )
        if family_rows.empty:
            continue
        if len(family_rows) > limit:
            positions = np.rint(np.linspace(0, len(family_rows) - 1, limit)).astype(int)
            family_rows = family_rows.iloc[np.unique(positions)]
        family_rows = family_rows.copy()
        family_rows["_family_available"] = family_sizes[family]
        sampled.append(family_rows)
    return pd.concat(sampled, ignore_index=False) if sampled else frame.iloc[0:0].copy()


def positive_runtime_rows(frame: pd.DataFrame, metric: str) -> pd.DataFrame:
    off_column = f"{metric}_off"
    on_column = f"{metric}_on"
    speedup_column = f"{metric}_speedup"
    if not {off_column, on_column}.issubset(frame.columns):
        return frame.iloc[0:0].copy()
    sub = frame.copy()
    for column in (off_column, on_column, speedup_column):
        if column in sub:
            sub[column] = pd.to_numeric(sub[column], errors="coerce")
    return sub.loc[
        np.isfinite(sub[off_column]) & sub[off_column].gt(0)
        & np.isfinite(sub[on_column]) & sub[on_column].gt(0)
        & ~timeout_mask(sub)
        & ~below_runtime_threshold(sub, metric)
    ].copy()


def plot_runtime_axis(
    ax: plt.Axes, frame: pd.DataFrame, metric: str, family: str, show_plan: bool
) -> None:
    off_column = f"{metric}_off"
    on_column = f"{metric}_on"
    speedup_column = f"{metric}_speedup"
    order_columns = [column for column in (speedup_column, "query") if column in frame]
    ascending = [False, True] if speedup_column in order_columns else [True]
    sub = frame.sort_values(order_columns, ascending=ascending, kind="stable")
    y = np.arange(len(sub))
    off = sub[off_column].to_numpy(float)
    on = sub[on_column].to_numpy(float)
    for row, off_value, on_value in zip(y, off, on):
        ax.plot(
            [off_value, on_value], [row, row], color="0.78", linewidth=0.45,
            solid_capstyle="round", zorder=1
        )
    ax.scatter(off, y, s=11, color=C_T1, edgecolor="none", zorder=3)
    ax.scatter(on, y, s=11, color=C_TM, edgecolor="none", zorder=4)

    labels = sub["display_query"].astype(str).tolist()
    if show_plan:
        plans = sub.get("selected_plan", pd.Series("", index=sub.index)).astype(str).str.upper()
        plan_tags = np.select(
            [plans.eq("OUTERYAN"), plans.eq("DUCKDB")], ["OuterYan", "DuckDB"], default="?"
        )
        labels = [f"{query} [{plan}]" for query, plan in zip(labels, plan_tags)]
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=4.5 if len(sub) > 45 else 5.2)
    ax.invert_yaxis()
    ax.set_xscale("log")
    values = np.concatenate([off, on])
    lower, upper = np.log10(values.min()), np.log10(values.max())
    padding = max(0.08, (upper - lower) * 0.04)
    ax.set_xlim(10 ** (lower - padding), 10 ** (upper + padding))
    ax.grid(axis="x", which="both", color="0.90", linewidth=0.45)
    ax.set_axisbelow(True)
    ax.set_xlabel(f"{metric.upper()} wall-clock time (seconds, log)", fontsize=8)
    ax.set_title(f"{family} (n={len(sub)})", fontsize=10)


def runtime_series(frame: pd.DataFrame) -> list[tuple[str, str, str]]:
    """New thread-tagged runs have only TM; legacy runs still require both pairs."""
    if "timing_threads" in frame and frame["timing_threads"].notna().all():
        counts = frame["timing_threads"].unique()
        if len(counts) == 1:
            return [
                (label.replace("Multi-thread", f"{int(counts[0])} threads"), column, color)
                for label, column, color in RUNTIME_SERIES[2:]
            ]
        return RUNTIME_SERIES[2:]
    return RUNTIME_SERIES


def complete_runtime_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep correct, non-timeout queries with complete timings for their schema."""
    correct = correctness_eligible(frame)
    sub = frame.loc[correct & ~timeout_mask(frame)].copy()
    complete = pd.Series(True, index=sub.index)
    for _, column, _ in runtime_series(frame):
        values = pd.to_numeric(
            sub.get(column, pd.Series(np.nan, index=sub.index)), errors="coerce"
        )
        valid = np.isfinite(values) & values.gt(0)
        sub[column] = values.where(valid)
        complete &= valid
    return sub.loc[complete & ~below_runtime_threshold(sub)].copy()


def selected_runtime_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep OuterYan-selected queries with complete timings for their schema."""
    plans = frame.get("selected_plan", pd.Series("", index=frame.index)).astype(str).str.upper()
    return complete_runtime_rows(frame.loc[plans.eq("OUTERYAN")])


def representative_runtime_rows(
    frame: pd.DataFrame, limit: int = REPRESENTATIVE_QUERIES_PER_FAMILY, scope: str = "outeryan",
    eligible_queries: set[tuple] | None = None,
    identity_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Per-family caps, round-robin shape quotas, then OFF-runtime quantiles.

    Eligibility requires complete timings, an eligible check status, and the requested plan scope.
    Neither speed-up nor ON time ranks eligible candidates. Keep label IDs from
    the full in-scope population so filtering and sampling do not renumber them.
    """
    if limit < 1:
        raise ValueError("representatives per benchmark must be positive")
    if scope not in ("all", "outeryan"):
        raise ValueError("representative scope must be all or outeryan")
    population = frame
    if scope == "outeryan":
        plans = frame.get("selected_plan", pd.Series("", index=frame.index)).astype(str).str.upper()
        population = frame.loc[plans.eq("OUTERYAN")]
    eligible = complete_runtime_rows(add_short_query_labels(population))
    if eligible_queries is not None:
        keys = identity_columns or query_identity_columns(eligible)
        eligible = eligible.loc[[
            key in eligible_queries for key in eligible[keys].itertuples(index=False, name=None)
        ]].copy()
    if eligible.empty:
        return eligible
    families = [family for family in FAMILY_ORDER if eligible["family"].eq(family).any()]
    baseline = "tm_off"
    sampled = []
    for family in families:
        candidates = eligible.loc[eligible["family"].eq(family)]
        target = min(limit, len(candidates))
        if target < limit:
            print(f"  representative sample: {family} has only {target} eligible queries (target {limit})")
        shapes = [shape for shape in TOPOLOGY_ORDER + ["other"] if candidates["topology"].eq(shape).any()]
        strata = {
            shape: candidates.loc[candidates["topology"].eq(shape)].sort_values(
                [baseline, "query"], kind="stable"
            ) for shape in shapes
        }
        quotas = dict.fromkeys(shapes, 0)
        for _ in range(target):
            available = [shape for shape in shapes if quotas[shape] < len(strata[shape])]
            shape = min(available, key=lambda value: quotas[value])
            quotas[shape] += 1
        if target < len(shapes):
            print(f"  representative sample: {family} has {len(shapes)} shapes but only {target} slots")
        for shape in shapes:
            count = quotas[shape]
            if not count:
                continue
            rows = strata[shape]
            positions = ([len(rows) // 2] if count == 1 else
                         np.rint(np.linspace(0, len(rows) - 1, count)).astype(int))
            chosen = rows.iloc[positions].copy()
            chosen["_family_available"] = len(candidates)
            sampled.append(chosen)
    return pd.concat(sampled, ignore_index=False)


def runtime_setting_label(frame: pd.DataFrame, metric: str) -> str:
    if metric == "tm" and "timing_threads" in frame:
        threads = pd.to_numeric(frame["timing_threads"], errors="coerce").dropna().unique()
        if len(threads) == 1:
            return f"{int(threads[0])} threads"
    return metric.upper()


def format_seconds_label(value: float) -> str:
    if value >= 100:
        return f"{value:.0f}s"
    if value >= 10:
        return f"{value:.1f}s"
    if value >= 1:
        return f"{value:.2g}s"
    if 0 < value < 0.01:
        return f"{value:.2g}s"
    return f"{value:.2f}s"


def format_speedup_label(value: float) -> str:
    if value >= 100:
        return f"{value:.0f}×"
    if value >= 10:
        return f"{value:.1f}×"
    return f"{value:.2f}×"


def style_log_runtime_axis(ax: plt.Axes, lower: float, upper: float) -> None:
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(lower, upper)
    ax.set_ylim(lower, upper)
    ax.plot([lower, upper], [lower, upper], color="0.55", linewidth=0.8, zorder=1)
    ax.tick_params(which="both", direction="in", top=True, right=True, length=3.5)
    ax.tick_params(which="minor", length=2.0)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(False)


def speedup_distribution(ax: plt.Axes, frame: pd.DataFrame, families: list[str]) -> None:
    """Draw compact log-speed-up violins with every query and robust summaries."""
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from matplotlib.patches import Polygon

    if not families:
        ax.text(0.5, 0.5, "No measured OuterYan-selected queries", transform=ax.transAxes,
                ha="center", va="center", color="0.45")
        ax.set_axis_off()
        return
    # Arrow + gap + plot match the runtime panel's height; direction labels sit
    # above that boundary and do not consume any of the shared panel height.
    panel_box = ax.get_position()
    arrow_gap, arrow_height = 0.012, 0.045
    panel_top = 1.0 + arrow_gap + arrow_height
    plot_height_fraction = 1.0 / panel_top
    ax.set_position([panel_box.x0, panel_box.y0, panel_box.width,
                     panel_box.height * plot_height_fraction])
    data = [
        np.log10(frame.loc[frame["family"].eq(family), "_speedup"].to_numpy(float))
        for family in families
    ]
    density_data = [
        values if len(values) > 1 and np.ptp(values) > 1e-12
        else np.asarray([values[0] - 0.015, values[0] + 0.015])
        for values in data
    ]
    positions = np.arange(len(families), dtype=float)
    violins = ax.violinplot(
        density_data, positions=positions, orientation="horizontal", widths=0.70,
        showmeans=False, showmedians=False, showextrema=False,
    )
    for body, family in zip(violins["bodies"], families):
        body.set_facecolor(FAMILY_COLORS[family])
        body.set_edgecolor(FAMILY_COLORS[family])
        body.set_alpha(0.18)
        body.set_linewidth(0.9)

    for position, family, values in zip(positions, families, data):
        ordered = np.sort(values)
        # Deterministic low-discrepancy jitter exposes density without suggesting
        # another measured variable on the y axis.
        jitter = ((np.arange(len(ordered)) * 0.61803398875) % 1.0 - 0.5) * 0.34
        color = FAMILY_COLORS[family]
        ax.scatter(
            ordered, position + jitter, s=QUERY_POINT_SIZE, color=color, edgecolor="white",
            linewidth=0.25, alpha=QUERY_POINT_ALPHA, zorder=3,
        )
        lower, median, upper = np.quantile(ordered, [0.25, 0.5, 0.75])
        ax.plot([lower, upper], [position, position], color=color, linewidth=3.0,
                solid_capstyle="round", zorder=4)
        ax.scatter(median, position, marker="D", s=25, color="white", edgecolor=color,
                   linewidth=1.0, zorder=5)

    all_values = np.concatenate(data)
    padding = max(0.08, (float(all_values.max()) - float(all_values.min())) * 0.04)
    # Always show the 1x reference, including when every selected plan wins or loses.
    lower = min(float(all_values.min() - padding), -padding)
    upper = max(float(all_values.max() + padding), padding)
    candidates = np.asarray([0.1, 0.25, 0.5, 1, 2, 4, 10, 25, 50, 100, 250], dtype=float)
    # Extend decade labels for large measured outliers without truncating them.
    if upper >= 3:
        candidates = np.concatenate((candidates, 10.0 ** np.arange(3, math.floor(upper) + 1)))
    ticks = np.log10(candidates)
    visible = (ticks >= lower) & (ticks <= upper)
    ax.set_xlim(lower, upper)
    ax.set_xticks(ticks[visible], [f"{value:g}×" for value in candidates[visible]])
    ax.set_yticks(positions, [figure_family_label(family) for family in families])
    ax.invert_yaxis()
    ax.axvline(0.0, color="0.45", linewidth=0.8, zorder=1)
    # Soft warm/cool hues meet at white for 1x. The background and arrow share the
    # same mapping in log space, with distinct slowdown and speed-up regions.
    color_map = LinearSegmentedColormap.from_list("speedup_background", [
        (0.0, "#F2DEE7"), (-lower / (upper - lower), "#FFFFFF"), (1.0, "#DDECF2"),
    ], N=1024)
    gradient = np.tile(np.linspace(lower, upper, 512), (2, 1))
    y_limits = ax.get_ylim()
    background = ax.imshow(
        gradient, extent=(lower, upper, min(y_limits), max(y_limits)), origin="lower",
        cmap=color_map, norm=Normalize(vmin=lower, vmax=upper),
        aspect="auto", interpolation="bilinear", zorder=0,
    )
    ax.set_ylim(y_limits)
    # Clip the colorbar to an arrow without extending its range: every color
    # stays aligned with the same speed-up on the plot's bottom axis.
    color_axis = ax.inset_axes([0.0, 1.0 + arrow_gap, 1.0, arrow_height])
    colorbar = ax.figure.colorbar(background, cax=color_axis, orientation="horizontal")
    colorbar.set_ticks([])
    colorbar.outline.set_visible(False)
    # Use the full strip height for the shaft, so its visible upper edge (not
    # empty space around an oversized arrowhead) aligns with the runtime plot.
    arrow = Polygon(
        [(0.0, 0.0), (0.978, 0.0), (1.0, 0.5), (0.978, 1.0), (0.0, 1.0)],
        transform=color_axis.transAxes, facecolor="none", edgecolor="0.60",
        linewidth=0.4, clip_on=False,
    )
    color_axis.add_patch(arrow)
    colorbar.solids.set_clip_path(arrow)
    ax.set_xlabel("DuckDB vs. OuterYan")
    ax.tick_params(axis="both", direction="in", top=True, right=True)
    ax.grid(axis="x", color="0.90", linewidth=0.55, zorder=0)
    ax.text(0.0, panel_top + 0.012, "OuterYan slower", transform=ax.transAxes, ha="left", va="bottom",
            fontsize=8, color="0.40")
    ax.text(1.0, panel_top + 0.012, "OuterYan faster", transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color="0.40")


def page_speedup_scatter(pdf: PdfPages, frame: pd.DataFrame, run: str, metric: str) -> None:
    """All measured runtimes and the OuterYan-selected speed-up distribution."""
    _load_plotting()
    correct = correctness_eligible(frame)
    sub = positive_runtime_rows(frame.loc[correct], metric)
    if sub.empty:
        print(f"  speed-up figure omitted for {run}: no complete timings")
        return
    sub["_speedup"] = sub[f"{metric}_off"] / sub[f"{metric}_on"]
    sub = sub.loc[np.isfinite(sub["_speedup"]) & sub["_speedup"].gt(0)]
    if sub.empty:
        return
    plans = sub.get("selected_plan", pd.Series("", index=sub.index)).astype(str).str.upper()
    distribution = sub.loc[plans.eq("OUTERYAN")].copy()
    families = [family for family in FAMILY_ORDER if sub["family"].eq(family).any()]
    distribution_families = [family for family in families if distribution["family"].eq(family).any()]
    off_column, on_column = f"{metric}_off", f"{metric}_on"
    values = np.concatenate([sub[off_column].to_numpy(float), sub[on_column].to_numpy(float)])
    log_min, log_max = np.log10(values.min()), np.log10(values.max())
    pad = max(0.08, (log_max - log_min) * 0.045)
    lower, upper = 10 ** (log_min - pad), 10 ** (log_max + pad)

    figure, axes = plt.subplots(
        1, 2, figsize=(11.0, 4.55), gridspec_kw={"width_ratios": [0.72, 1.0]}
    )
    figure.subplots_adjust(left=0.075, right=0.99, bottom=0.16, top=0.88, wspace=0.08)
    family_axis, distribution_axis = axes

    for family in families:
        rows = sub.loc[sub["family"].eq(family)].sort_values("query", kind="stable")
        faster = rows[on_column].le(rows[off_column])
        family_axis.scatter(
            rows.loc[faster, off_column], rows.loc[faster, on_column], marker="o",
            s=QUERY_POINT_SIZE,
            color=FAMILY_COLORS[family], edgecolor="white", linewidth=0.25,
            alpha=QUERY_POINT_ALPHA, zorder=3,
        )
        family_axis.scatter(
            rows.loc[~faster, off_column], rows.loc[~faster, on_column], marker="X",
            s=QUERY_POINT_SIZE, color=FAMILY_COLORS[family], edgecolor="white",
            linewidth=0.20,
            alpha=QUERY_POINT_ALPHA, zorder=4,
        )
    style_log_runtime_axis(family_axis, lower, upper)
    family_axis.fill_between(
        [lower, upper], [lower, lower], [lower, upper], color="#EFF6F9", zorder=0,
    )
    family_axis.set_xlabel("DuckDB running time (s)")
    family_axis.set_ylabel("OuterYan running time (s)")
    legend_handles = [tuple([
        Line2D([], [], color=FAMILY_COLORS[family], marker="o", linestyle="none",
               markeredgecolor="white", markeredgewidth=0.25, markersize=6),
        Line2D([], [], color=FAMILY_COLORS[family], marker="X", linestyle="none",
               markeredgecolor="white", markeredgewidth=0.20, markersize=5.6),
    ])
        for family in families
    ]
    legend_labels = [figure_family_label(family) for family in families]
    legend_handles.extend([
        Line2D([], [], color="0.28", marker="o", linestyle="none", markeredgecolor="white",
               markeredgewidth=0.25, markersize=6),
        Line2D([], [], color="0.28", marker="X", linestyle="none", markeredgecolor="white",
               markeredgewidth=0.20, markersize=5.6),
    ])
    legend_labels.extend(["OuterYan faster/equal", "OuterYan slower"])
    figure.legend(
        handles=legend_handles, labels=legend_labels,
        handler_map={tuple: HandlerTuple(ndivide=None, pad=0.18)},
        ncol=len(legend_handles), loc="upper center",
        bbox_to_anchor=(0.5, 0.965), frameon=False, borderaxespad=0.0,
        handlelength=1.7, handletextpad=0.30, columnspacing=0.72,
    )
    speedup_distribution(distribution_axis, distribution, distribution_families)

    for label, axis in zip(
        ("(a) Running Time Comparison", "(b) Speed-up Comparison"), axes
    ):
        label_y = -0.125 * family_axis.get_position().height / axis.get_position().height
        axis.text(0.5, label_y, label, transform=axis.transAxes, ha="center", va="top",
                  fontsize=11, fontweight="semibold")
    save_page(pdf, figure)


def complete_phase_rows(
    frame: pd.DataFrame, *, include_duckdb_timeouts: bool = False,
) -> tuple[pd.DataFrame, int]:
    """Validate OuterYan profiles, optionally independent of baseline timeouts.

    Legacy paired reports retain their complete-pair policy by default. An
    OuterYan-only phase summary may include an OFF timeout only with explicit
    evidence of completed ON timing and profiling, never imputed phase times.
    """
    seconds_columns = [seconds for _, seconds, _, _ in PHASES]
    ratio_columns = [ratio for _, _, ratio, _ in PHASES]
    wall_column = "profile_wall_time_s" if "profile_wall_time_s" in frame else "profile_total_time_s"
    required = seconds_columns + ratio_columns + [wall_column]
    if not set(required).issubset(frame.columns):
        return frame.iloc[0:0].copy(), 0
    plans = frame.get("selected_plan", pd.Series("", index=frame.index)).astype(str).str.upper()
    correct = correctness_eligible(frame)
    eligible = correct & ~timeout_mask(frame)
    if include_duckdb_timeouts:
        def status(column):
            return frame.get(column, pd.Series("", index=frame.index)).fillna("").astype(str).str.upper()

        on_time = pd.to_numeric(frame.get("tm_on", pd.Series(np.nan, index=frame.index)), errors="coerce")
        on_stage = status("outeryan_timeout_stage").str.strip()
        unchecked = status("correct").eq("NOT-CHECKED") & status("correctness_check").eq("DISABLED")
        baseline_only = (
            status("duckdb_status").eq("TIMEOUT")
            & status("outeryan_status").eq("MEASURED")
            & status("profile_status").eq("OK")
            & (status("correct").eq("TRUE") | unchecked)
            & on_stage.isin(("", "-", "NA", "N/A", "NAN", "NONE", "NULL", "NOT-RUN"))
            & ~status("outeryan_correctness_status").isin(("FALSE", "ERROR", "NOT-EQUIV", "TIMEOUT"))
            & np.isfinite(on_time) & on_time.gt(0)
        )
        eligible |= baseline_only
    selected = frame.loc[plans.eq("OUTERYAN") & eligible & ~below_runtime_threshold(frame)].copy()
    if selected.empty:
        return selected, 0
    for column in list(dict.fromkeys(
        required + ["profile_threads", "profile_total_time_s", "profile_cpu_time_s"]
    )):
        if column in selected:
            selected[column] = pd.to_numeric(selected[column], errors="coerce")
    seconds = selected[seconds_columns]
    ratios = selected[ratio_columns]
    wall_time = selected[wall_column]
    reported_total = selected.get(
        "profile_total_time_s", pd.Series(np.nan, index=selected.index)
    )
    cpu_time = selected.get("profile_cpu_time_s", reported_total).where(
        lambda value: np.isfinite(value) & value.gt(0), reported_total
    )
    new_schema = "profile_wall_time_s" in frame
    total_matches_cpu = (
        np.isclose(reported_total, cpu_time, rtol=1e-9, atol=1e-9)
        if new_schema else np.ones(len(selected), dtype=bool)
    )
    complete = (
        np.isfinite(seconds).all(axis=1)
        & seconds.ge(0).all(axis=1)
        & np.isfinite(ratios).all(axis=1)
        & ratios.ge(0).all(axis=1)
        & ratios.le(1).all(axis=1)
        & np.isfinite(wall_time)
        & wall_time.gt(0)
        & np.isfinite(cpu_time)
        & cpu_time.gt(0)
        & total_matches_cpu
        & np.isclose(seconds.sum(axis=1), cpu_time, rtol=1e-6, atol=1e-9)
        & ratios.sum(axis=1).sub(1.0).abs().le(1e-6)
        & np.isclose(
            ratios.to_numpy(float), seconds.div(cpu_time, axis=0).to_numpy(float), atol=1e-6
        ).all(axis=1)
    )
    selected["_profile_wall_time"] = wall_time
    selected["_profile_cpu_time"] = cpu_time
    selected["_phase_sum_s"] = seconds.sum(axis=1)
    selected["_phase_sum_error_s"] = selected["_phase_sum_s"] - cpu_time
    return selected.loc[complete].copy(), int((~complete).sum())


def phase_source(
    frame: pd.DataFrame, placeholder: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, str | None]:
    """Prefer current profiles; an explicit legacy fallback is never merged in."""
    if placeholder is None or not complete_phase_rows(frame)[0].empty:
        return frame, None
    eligible, _ = complete_phase_rows(placeholder)
    if eligible.empty:
        raise ValueError("Phase placeholder input has no complete OuterYan profiles")
    runs = eligible["run"].dropna().unique()
    threads = eligible.get("profile_threads", pd.Series(dtype=float))
    known_thread_count = (
        len(threads) == len(eligible) and threads.notna().all()
        and threads.nunique() == 1 and np.isfinite(threads).all()
        and (threads.gt(0) & threads.eq(np.floor(threads))).all()
    )
    if len(runs) != 1 or not known_thread_count:
        raise ValueError("Phase placeholder must identify one run and one known profile thread count")
    run = str(runs[0])
    date = f"{run[:4]}-{run[4:6]}-{run[6:8]}" if re.match(r"^\d{8}_", run) else run
    timing_threads = pd.to_numeric(frame.get("timing_threads", pd.Series(dtype=float)), errors="coerce")
    current_label = "current run"
    if timing_threads.nunique() == 1 and np.isfinite(timing_threads).all():
        current_label = f"current {int(timing_threads.iloc[0])}-thread"
    notice = (
        f"PLACEHOLDER: {date} profiles, {int(threads.iloc[0])} threads "
        f"(not {current_label} results)"
    )
    return placeholder, notice


def phase_baseline_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Match native profiles to unprofiled OFF timing from the same run/threads.

    The legacy dual-thread CSV schema profiles its TM configuration by contract;
    current CSVs explicitly record timing_threads, which must match the profile.
    Never use a current runtime sample's timing as a legacy profile's baseline.
    """
    rows, _ = complete_phase_rows(frame)
    if rows.empty:
        return rows
    missing = pd.Series(np.nan, index=rows.index)
    threads = pd.to_numeric(rows.get("profile_threads", missing), errors="coerce")
    timing_threads = pd.to_numeric(rows.get("timing_threads", missing), errors="coerce")
    legacy = timing_threads.isna() & {"t1_off", "tm_off"}.issubset(rows.columns)
    baseline = pd.Series(np.nan, index=rows.index)
    for column, matches in (
        ("tm_off", threads.gt(1) & (threads.eq(timing_threads) | legacy)),
        ("t1_off", threads.eq(1) & legacy),
    ):
        values = pd.to_numeric(rows.get(column, missing), errors="coerce")
        baseline.loc[matches] = values.loc[matches]
    valid = np.isfinite(baseline) & baseline.gt(0) & np.isfinite(threads)
    rows["baseline_time_s"] = baseline
    rows["baseline_threads"] = threads
    return rows.loc[valid].copy()


def paired_representative_samples(
    frame: pd.DataFrame, phase_frame: pd.DataFrame, limit: int = REPRESENTATIVE_QUERIES_PER_FAMILY,
    scope: str = "outeryan",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Use one sample, short-ID mapping and order for runtime and phase figures."""
    profiles = phase_baseline_rows(phase_frame)
    has_profiles = not complete_phase_rows(phase_frame)[0].empty
    join_keys = [key for key in query_identity_columns(frame) if key in profiles]
    keys = set(profiles[join_keys].itertuples(index=False, name=None))
    sample = representative_runtime_rows(
        frame, limit, scope, eligible_queries=keys if has_profiles and scope == "outeryan" else None,
        identity_columns=join_keys,
    )
    if profiles.empty or sample.empty:
        return sample, profiles.iloc[0:0].copy()
    identity = join_keys + ["short_query", "topology", "_family_available"]
    paired = sample[identity].merge(
        profiles.drop(columns=[c for c in identity if c not in join_keys], errors="ignore"),
        on=join_keys, how="inner", sort=False, validate="one_to_one",
    )
    return sample, paired


def phase_group_layout(
    frame: pd.DataFrame, families: list[str], gap: float = PHASE_GROUP_GAP,
) -> tuple[np.ndarray, dict[str, float], list[float]]:
    """Return compact row positions with one visible gap between benchmarks."""
    positions: list[float] = []
    centers: dict[str, float] = {}
    separators: list[float] = []
    cursor = 0.0
    for family_index, family in enumerate(families):
        count = int(frame["family"].eq(family).sum())
        group = cursor + np.arange(count, dtype=float)
        positions.extend(group.tolist())
        centers[family] = float((group[0] + group[-1]) / 2.0)
        cursor = float(group[-1] + 1.0)
        if family_index < len(families) - 1:
            separators.append(cursor - 0.5 + gap / 2.0)
            cursor += gap
    return np.asarray(positions, dtype=float), centers, separators


def diverse_phase_samples(
    frame: pd.DataFrame, limit: int = 4, max_other_share: float = 0.5,
) -> pd.DataFrame:
    """Sample distinct phase compositions among measured speed-ups >= 1.

    Prefer Other OP <= max_other_share. If a family cannot fill its quota,
    restrict it to the lowest-Other OP candidates needed to fill that quota.
    Start at the composition nearest the family centroid, then maximize the
    distance to the closest selected composition. Query identity breaks ties;
    speed-up magnitude is not a ranking criterion. This display filter must
    never be used to compute cohort statistics.
    """
    if limit < 1:
        raise ValueError("Phase sample size must be positive")
    if not np.isfinite(max_other_share) or not 0 <= max_other_share <= 1:
        raise ValueError("Other OP share limit must be between zero and one")
    labeled = frame if "short_query" in frame else add_short_query_labels(frame)
    rows = phase_baseline_rows(labeled)
    rows = complete_runtime_rows(rows)
    if rows.empty:
        return rows
    off = pd.to_numeric(rows["baseline_time_s"], errors="coerce")
    on = pd.to_numeric(rows["tm_on"], errors="coerce")
    rows = rows.loc[np.isfinite(on) & on.gt(0) & off.ge(on)]
    columns = [seconds for _, seconds, _, _ in PHASES]
    chosen = []
    for family in FAMILY_ORDER:
        candidates = rows.loc[rows.family.eq(family)].sort_values(query_identity_columns(rows), kind="stable")
        if candidates.empty:
            continue
        available = len(candidates)
        other = candidates["profile_other_elapsed_s"] / candidates["_profile_cpu_time"]
        eligible = candidates.loc[other.le(max_other_share)]
        relaxed = len(eligible) < min(limit, available)
        if relaxed:
            # Stable sort keeps identity tie-breaking independent of input order.
            candidates = candidates.loc[other.sort_values(kind="stable").index[:limit]]
            candidates = candidates.sort_values(query_identity_columns(rows), kind="stable")
        else:
            candidates = eligible
        shares = candidates[columns].to_numpy(float) / candidates["_profile_cpu_time"].to_numpy(float)[:, None]
        selected = [int(np.argmin(np.sum((shares - shares.mean(axis=0)) ** 2, axis=1)))]
        while len(selected) < min(limit, len(candidates)):
            distances = np.min(np.sum((shares[:, None, :] - shares[selected][None, :, :]) ** 2, axis=2), axis=1)
            distances[selected] = -1
            selected.append(int(np.argmax(distances)))
        sample = candidates.iloc[selected].copy()
        sample["_family_available"] = len(candidates)
        sample["_family_speedups"] = available
        sample["_phase_other_limit"] = max_other_share
        sample["_phase_other_limit_relaxed"] = relaxed
        chosen.append(sample)
    return pd.concat(chosen) if chosen else rows.iloc[:0].copy()


def page_phase(
    pdf: PdfPages, frame: pd.DataFrame, run: str, notice: str | None = None, preselected: bool = False,
) -> None:
    _load_plotting()
    sub, skipped = complete_phase_rows(frame)
    if sub.empty:
        print(f"  phase breakdown omitted for {run}: no complete selected profiles")
        return
    if not preselected:
        sub = sample_phase_queries(add_short_query_labels(sub))
    topology_rank = {name: index for index, name in enumerate(TOPOLOGY_ORDER + ["other"])}
    sub = sub.copy()
    sub["_topology_rank"] = sub["topology"].map(topology_rank).fillna(99)
    family_rank = {family: index for index, family in enumerate(FAMILY_ORDER)}
    sub["_family_rank"] = sub["family"].map(family_rank).fillna(99)
    sub = sub.sort_values(
        ["_family_rank", "_topology_rank", "short_query"], kind="stable"
    )
    seconds_columns = [seconds for _, seconds, _, _ in PHASES]
    families = [family for family in FAMILY_ORDER if sub["family"].eq(family).any()]
    missing = pd.Series(np.nan, index=sub.index)
    baseline_source = sub["baseline_time_s"] if "baseline_time_s" in sub else sub.get("tm_off", missing)
    baseline_runtime = pd.to_numeric(baseline_source, errors="coerce").to_numpy(float)
    outeryan_runtime = pd.to_numeric(sub.get("tm_on", missing), errors="coerce").to_numpy(float)
    runtime_valid = (
        np.isfinite(baseline_runtime) & (baseline_runtime > 0)
        & np.isfinite(outeryan_runtime) & (outeryan_runtime > 0)
    )
    has_runtime_comparison = bool(runtime_valid.any())
    runtime_speedup = np.divide(
        baseline_runtime, outeryan_runtime,
        out=np.full_like(baseline_runtime, np.nan), where=runtime_valid,
    )
    height = max(3.1, 1.25 + 0.215 * len(sub) + 0.10 * max(len(families) - 1, 0))
    if has_runtime_comparison:
        figure, (axis, runtime_axis) = plt.subplots(
            1, 2, sharey=True, figsize=(15.1, height),
            gridspec_kw={"width_ratios": [5.15, 1.30], "wspace": 0.075},
        )
    else:
        figure, axis = plt.subplots(figsize=(13.4, height))
        runtime_axis = None
    maximum_total = float(sub["_profile_cpu_time"].max())
    label_space = max(9.0, len(f"{maximum_total:.1f} s") * 1.25)
    y, family_centers, group_separators = phase_group_layout(sub, families)
    totals = sub["_profile_cpu_time"].to_numpy(float)
    phase_values = sub[seconds_columns].to_numpy(float)
    shares = np.divide(
        phase_values, totals[:, None], out=np.zeros_like(phase_values), where=totals[:, None] > 0
    ) * 100.0
    left = np.zeros(len(sub), dtype=float)
    for phase_index, (label, _, _, color) in enumerate(PHASES):
        widths = shares[:, phase_index]
        axis.barh(
            y, widths, left=left, height=0.54, color=color, edgecolor="white",
            linewidth=0.30, label=label,
        )
        seconds = phase_values[:, phase_index]
        for row_y, start, width_value, seconds_value in zip(y, left, widths, seconds):
            if width_value >= 9.0:
                axis.text(
                    start + width_value / 2.0, row_y, format_seconds_label(seconds_value),
                    ha="center", va="center", fontsize=7,
                    color="white" if color != "#A0A0A0" else "black",
                )
        left += widths
    for row_y, total in zip(y, totals):
        total_label = f"{total:.3g} s" if total < 0.1 else f"{total:.1f} s"
        axis.text(101.2, row_y, total_label, ha="left", va="center", fontsize=8)

    versioned_labels = "workload_category" in sub
    for family in families:
        axis.text(
            -0.110 if versioned_labels else -0.074,
            family_centers[family], figure_family_label(family),
            transform=axis.get_yaxis_transform(), rotation=90,
            ha="center", va="center", fontsize=9.5, fontweight="semibold", clip_on=False,
        )
    for separator in group_separators:
        axis.axhline(separator, color="0.43", linewidth=0.8, zorder=6)
        if runtime_axis is not None:
            runtime_axis.axhline(separator, color="0.43", linewidth=0.8, zorder=6)

    axis.set_xlim(0, 100 + label_space)
    axis.set_yticks(y, sub["short_query"])
    axis.set_ylim(y[-1] + 0.50, y[0] - 0.50)
    axis.set_xlabel("CPU Time (%)")
    axis.set_xticks([0, 25, 50, 75, 100])
    axis.tick_params(axis="both", direction="in", top=True, right=True)
    axis.grid(False)
    axis.text(
        1.0, 1.015, PROFILE_CPU_TOTAL_LABEL,
        transform=axis.transAxes, ha="right", va="bottom", fontsize=8, color="0.30",
    )
    if runtime_axis is not None:
        for row_y, baseline, outeryan, valid in zip(
            y, baseline_runtime, outeryan_runtime, runtime_valid
        ):
            if valid:
                runtime_axis.plot(
                    [baseline, outeryan], [row_y, row_y], color="0.72", linewidth=1.0, zorder=1,
                )
        runtime_axis.scatter(
            baseline_runtime[runtime_valid], y[runtime_valid], marker="o", s=38,
            color=PHASE_RUNTIME_DUCKDB_COLOR, edgecolor=PHASE_RUNTIME_EDGE_COLOR,
            linewidth=0.45, zorder=3,
        )
        runtime_axis.scatter(
            outeryan_runtime[runtime_valid], y[runtime_valid], marker="D", s=42,
            color=PHASE_RUNTIME_OUTERYAN_COLOR, edgecolor=PHASE_RUNTIME_EDGE_COLOR,
            linewidth=0.45, zorder=4,
        )
        runtime_values = np.concatenate([
            baseline_runtime[runtime_valid], outeryan_runtime[runtime_valid]
        ])
        log_min, log_max = np.log10(runtime_values.min()), np.log10(runtime_values.max())
        pad = max(0.08, (log_max - log_min) * 0.06)
        runtime_axis.set_xscale("log")
        runtime_axis.set_xlim(10 ** (log_min - pad), 10 ** (log_max + pad))
        runtime_axis.set_xlabel("Running time: DuckDB vs. OuterYan")
        runtime_axis.set_axisbelow(True)
        runtime_axis.tick_params(axis="x", which="both", direction="in", top=True)
        runtime_axis.tick_params(axis="y", left=False, right=True, labelleft=False)
        runtime_axis.grid(axis="x", which="major", color="0.90", linewidth=0.55, zorder=0)
        runtime_axis.grid(axis="x", which="minor", color="0.96", linewidth=0.35, zorder=0)
        for row_y, speedup, valid in zip(y, runtime_speedup, runtime_valid):
            if valid:
                runtime_axis.text(
                    1.040, row_y, format_speedup_label(speedup),
                    transform=runtime_axis.get_yaxis_transform(), ha="left", va="center",
                    fontsize=8.0, color="0.25", clip_on=False,
                )
    if skipped:
        print(f"  phase breakdown for {run}: {skipped} incomplete selected profiles omitted")
    if notice:
        figure.text(0.52, 0.982, notice, ha="center", va="center", fontsize=10, color="#9A4E16")
    phase_handles = [
        Patch(facecolor=color, edgecolor="none", label=label)
        for label, _, _, color in PHASES
    ]
    axis.legend(
        handles=phase_handles, ncol=4, fontsize=9.8, loc="lower center", frameon=False,
        bbox_to_anchor=(0.47 if versioned_labels else 0.50, 1.002), borderaxespad=0.08,
    )
    if runtime_axis is not None:
        runtime_axis.legend(
            handles=[
                Line2D([], [], color=PHASE_RUNTIME_DUCKDB_COLOR, marker="o", linestyle="none",
                       markeredgecolor=PHASE_RUNTIME_EDGE_COLOR, markeredgewidth=0.45,
                       markersize=5.8, label="DuckDB"),
                Line2D([], [], color=PHASE_RUNTIME_OUTERYAN_COLOR, marker="D", linestyle="none",
                       markeredgecolor=PHASE_RUNTIME_EDGE_COLOR, markeredgewidth=0.45,
                       markersize=6.0, label="OuterYan"),
            ],
            ncol=2, fontsize=9.2, loc="lower center", frameon=False,
            bbox_to_anchor=(0.50, 1.002), borderaxespad=0.08,
            columnspacing=0.8, handletextpad=0.35,
        )
    figure.subplots_adjust(left=0.135 if versioned_labels else 0.116,
                           right=0.932, bottom=max(0.105, 0.56 / height),
                           top=0.865 if notice else 0.910)
    # Anchor the key to the rendered labels, not a fixed canvas margin.
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    label_bottom = min(ax.xaxis.label.get_window_extent(renderer).y0 for ax in figure.axes)
    footer_y = (label_bottom - 3 * figure.dpi / 72) / figure.bbox.height
    figure.text(0.52, footer_y, QUERY_CODE_KEY, ha="center", va="top", fontsize=8.4)
    with plt.rc_context({"savefig.pad_inches": .04}):
        save_page(pdf, figure)


def page_run_comparison(pdf: PdfPages, frame: pd.DataFrame) -> None:
    _load_plotting()
    runs = list(dict.fromkeys(frame["run"]))
    if len(runs) < 2:
        return
    pivot = frame.pivot_table(
        index=query_identity_columns(frame), columns="run", values="tm_speedup", aggfunc="median"
    )
    pair = pivot[runs[:2]].dropna()
    if len(pair) < 2:
        return
    first, second = runs[:2]
    figure, ax = plt.subplots(figsize=(7, 6.5))
    ax.scatter(pair[first], pair[second], s=25, alpha=0.7, color=C_T1,
               edgecolor="black", linewidth=0.25)
    lower = max(0.005, min(pair.min().min(), 0.1))
    upper = pair.max().max() * 1.3
    ax.plot([lower, upper], [lower, upper], color="grey", linestyle="--")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(f"TM speed-up — {first}")
    ax.set_ylabel(f"TM speed-up — {second}")
    ax.set_title("Per-query run comparison")
    figure.tight_layout()
    save_page(pdf, figure)


def resolve_inputs(patterns: list[str], base_directory: Path) -> list[str]:
    paths: list[str] = []
    for pattern in patterns:
        expanded = os.path.expanduser(pattern)
        if not os.path.isabs(expanded):
            expanded = str(base_directory / expanded)
        hits = sorted(glob.glob(expanded))
        paths.extend(hits if hits else ([] if any(char in pattern for char in "*?[") else [expanded]))
    return list(dict.fromkeys(path for path in paths if path.lower().endswith(".csv")))


def remove_generated_file(path: Path) -> None:
    """Remove an obsolete output if present, using the Python 3.7 pathlib API."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def write_standalone_runtime_figures(
    output_directory: Path, frame: pd.DataFrame, run: str, metric: str,
    sample_per_family: int = REPRESENTATIVE_QUERIES_PER_FAMILY,
    representative_scope: str = "outeryan",
    phase_placeholder: pd.DataFrame | None = None,
    phase_sample_per_family: int | None = None,
) -> list[Path]:
    """Write the all-query comparison and optional representative phase breakdown."""
    output_directory.mkdir(parents=True, exist_ok=True)
    # Remove files emitted by the retired representative-runtime design so a
    # rerun in an existing results directory cannot leave obsolete figures.
    for filename in (
        "runtime_outeryan_queries.pdf", "runtime_outeryan_queries.png",
        "runtime_representative_queries.pdf", "runtime_representative_queries.png",
        "representative_queries.json",
    ):
        remove_generated_file(output_directory / filename)
    outputs = []
    correct = correctness_eligible(frame)
    if not positive_runtime_rows(frame.loc[correct], metric).empty:
        outputs.append(("speedup_all_queries", lambda pdf: page_speedup_scatter(pdf, frame, run, metric)))
    else:
        for suffix in (".pdf", ".png"):
            remove_generated_file(output_directory / ("speedup_all_queries" + suffix))
    phase_frame, notice = phase_source(frame, phase_placeholder)
    if phase_sample_per_family is None:
        _, phases = paired_representative_samples(frame, phase_frame, sample_per_family, representative_scope)
    else:
        phases = diverse_phase_samples(phase_frame, phase_sample_per_family)
    if not phases.empty:
        outputs.append(("phase_breakdown_outeryan", lambda pdf: page_phase(pdf, phases, run, notice, True)))
        columns = [column for column in (
            "run", "source_run", "source_csv", "workload_category", "query", "short_query", "family", "topology", "selected_plan", "profile_threads",
            "profile_round1_operator_s", "profile_round2_operator_s", "profile_round3_operator_s",
            "profile_other_elapsed_s", "profile_wall_time_s", "profile_total_time_s",
            "profile_cpu_time_s",
            "_phase_sum_s", "_phase_sum_error_s", "baseline_time_s", "tm_on", "baseline_threads",
            "_family_available", "_family_speedups", "_phase_other_limit", "_phase_other_limit_relaxed",
        ) if column in phases]
        (output_directory / "phase_queries.json").write_text(json.dumps({
            "placeholder": notice is not None,
            "notice": notice,
            "runtime_filter": runtime_filter_description(),
            "selection": ("phase-share farthest-point sample; speed-up >= 1; Other OP <= 50%; "
                          "if insufficient, use the lowest-Other OP queries needed to fill the family quota"
                          if phase_sample_per_family is not None else "shape and baseline-runtime ranks"),
            "queries": json.loads(phases[columns].to_json(orient="records", double_precision=15)),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        for filename in ("phase_breakdown_outeryan.pdf", "phase_breakdown_outeryan.png", "phase_queries.json"):
            remove_generated_file(output_directory / filename)
    paths: list[Path] = []
    for stem, draw in outputs:
        paths.append(write_figure_pair(output_directory, stem, draw))
    return paths



# ---- Machine-readable report metadata ---------------------------------------

FAMILIES = ("Graph", "TPC-H", "TPC-DS", "JOB", "All")
DIMENSIONS = ("family", "workload_category", "tree_shape", "join_graph_topology",
              "join_type_composition", "selectivity_level")








def family_summaries(detail: pd.DataFrame) -> list[dict]:
    return [{"family": family, **summarize(
        detail if family == "All" else detail.loc[detail["family"].eq(family)]
    )} for family in FAMILIES]


def composition(frame: pd.DataFrame) -> dict:
    """Count the supplied cohort, preserving the ablation stratum."""
    components = frame.get("workload_component", pd.Series("unknown", index=frame.index)).fillna("unknown")
    counts = components.value_counts()
    structural = int(counts.get("structural", 0))
    controls = int(counts.get("evaluation", 0))
    stress = int(counts.get("selectivity_ablation", 0))
    recovery = int(counts.get("historical_recovery", 0))
    return {
        "total": len(frame), "structural": structural,
        "supplementary": controls + stress + recovery, "supplementary_controls": controls,
        "selectivity_ablation": stress, "historical_recovery": recovery,
        "unclassified": len(frame) - structural - controls - stress - recovery,
        "rule": "core = structural; graph queries, selectivity ablation and historical recovery = supplementary",
        "dimensions": {
            dimension: {str(key): int(value) for key, value in frame[dimension].fillna("unspecified").value_counts().sort_index().items()}
            for dimension in DIMENSIONS if dimension in frame
        },
    }


def query_sql_path(row: pd.Series) -> Path:
    """Resolve the versioned SQL named by the original experiment record."""
    relative = row.get("sql_path")
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{row['query']}: sql_path is required to count participating columns")
    path = Path(relative)
    if ".." in path.parts:
        raise ValueError(f"{row['query']}: unsafe SQL path: {relative}")
    if path.is_absolute():
        if path.is_file():
            return path
        raise FileNotFoundError(path)
    return resolve_sql_path(row.get("original_workload_category", row.get("workload_category", "join")),
                            row.get("original_sql_path", path),
                            SCRIPT_DIR / "outerjoin_benchmark")


def database_columns(family: str) -> dict:
    """Read catalog metadata only; never execute a benchmark query for statistics."""
    name = {"Graph": "graph", "TPC-H": "tpch", "TPC-DS": "tpcds", "JOB": "job"}[family]
    root = SCRIPT_DIR.parent
    database = Path(os.environ.get(name.upper() + "_DB", str(root / (name + "_db")))).expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"Set {name.upper()}_DB to an existing database to expand SELECT *: {database}")
    binary = os.environ.get("DUCKDB_BIN")
    if binary:
        binary = shutil.which(binary) or str(Path(binary).expanduser().resolve())
    else:
        binary = next((str(root / "build" / mode / "duckdb") for mode in ("release", "debug")
                       if (root / "build" / mode / "duckdb").is_file()), None)
    if not binary:
        raise FileNotFoundError("Set DUCKDB_BIN to the DuckDB CLI to read column metadata")
    sql = ("SET disabled_optimizers TO 'outer_yan'; "
           "SELECT table_name, column_name FROM information_schema.columns "
           "WHERE table_catalog = current_database() AND table_schema = 'main' "
           "ORDER BY table_name, ordinal_position;")
    result = subprocess.run([binary, str(database), "-readonly", "-no-init", "-batch", "-bail", "-json", "-c", sql],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"Could not read {family} schema: {result.stderr.strip()}")
    tables = {}
    for column in json.loads(result.stdout):
        tables.setdefault(column["table_name"].casefold(), []).append(column["column_name"].casefold())
    return {"database": str(database), "tables": tables}


SQL_ATTRIBUTE_TOKENS = re.compile(
    r"(?P<comment>--[^\n]*|/\*.*?\*/)|(?P<string>'(?:''|[^'])*')|"
    r'(?P<quoted>"(?:""|[^"])*")|(?P<word>[A-Za-z_][A-Za-z_0-9$]*)|'
    r"(?P<number>\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)|(?P<symbol>[^\s])", re.DOTALL
)
SQL_ATTRIBUTE_KEYWORDS = set("""
SELECT DISTINCT FROM INNER LEFT RIGHT FULL OUTER CROSS JOIN ON WHERE GROUP BY HAVING ORDER
ASC DESC NULLS FIRST LAST LIMIT OFFSET AS AND OR NOT NULL IS IN BETWEEN LIKE ILIKE TRUE FALSE
CASE WHEN THEN ELSE END FILTER OVER PARTITION ROWS RANGE UNBOUNDED PRECEDING FOLLOWING CURRENT ROW
CAST TRY_CAST INTEGER BIGINT SMALLINT TINYINT DOUBLE FLOAT DECIMAL NUMERIC VARCHAR DATE TIMESTAMP INTERVAL
""".lower().split())


def participating_columns(sql: str, schema: dict[str, list[str]]) -> list[str]:
    """Resolve distinct alias.column references in the generated single-SELECT join corpus.

    A lexer separates identifiers from comments/literals. Stars in the SELECT
    list expand through the catalog; COUNT(*) has no column argument. Unsupported
    scopes are rejected except for the generator's Graph input-filter scans.
    """
    tokens = []
    for match in SQL_ATTRIBUTE_TOKENS.finditer(sql):
        kind, value = match.lastgroup, match.group()
        if kind == "comment":
            continue
        if kind == "quoted":
            value = value[1:-1].replace('""', '"')
        tokens.append((kind, value.casefold() if kind in ("word", "quoted") else value))
    # Graph inputcap1 scans project both graph columns without renaming. Collapse
    # only that exact leaf form for analysis, retaining its column dependencies.
    # This does not rewrite the executed SQL or accept arbitrary nested scopes.
    scan_columns, flattened, index = set(), [], 0
    while index < len(tokens):
        scan = tokens[index:index + 14]
        if (len(scan) == 14 and scan[:6] == [
                ("symbol", "("), ("word", "select"), ("word", "src"),
                ("symbol", ","), ("word", "dst"), ("word", "from")]
                and scan[6][0] == "word" and re.fullmatch(r"r[0-9]+", scan[6][1])
                and scan[7:11] == [("word", "where"), ("word", "src"),
                                   ("symbol", "<"), ("symbol", "=")]
                and scan[11][0] == "number" and re.fullmatch(r"[0-9]+", scan[11][1])
                and scan[12] == ("symbol", ")") and scan[13] == scan[6]):
            table = scan[6][1]
            if set(schema.get(table, [])) != {"src", "dst"}:
                raise ValueError(f"Graph input-filter scan requires the two-column src/dst schema: {table}")
            scan_columns.update((f"{table}.src", f"{table}.dst"))
            flattened.extend((scan[6], scan[13]))
            index += 14
            continue
        flattened.append(tokens[index])
        index += 1
    tokens = flattened
    words = [value for kind, value in tokens if kind == "word"]
    unsupported = set(words) & {"with", "union", "except", "intersect", "using", "natural", "columns",
                                "exclude", "replace", "pivot", "unpivot", "lateral"}
    if words.count("select") != 1 or unsupported or not tokens or tokens[0] != ("word", "select"):
        raise ValueError("Attribute counting requires the generated single-SELECT join form without CTEs/subqueries/USING")
    if any(value == ";" for _, value in tokens[:-1]):
        raise ValueError("Attribute counting accepts one SQL statement")
    identifiers = {index for index, (kind, _) in enumerate(tokens) if kind in ("word", "quoted")}
    values = [value for _, value in tokens]
    consumed, aliases, output_aliases = set(), {}, set()
    for index, token in enumerate(tokens):
        if token not in (("word", "from"), ("word", "join")):
            continue
        end = index + 1
        while end < len(tokens) and values[end] == "(":
            end += 1
        if end not in identifiers:
            raise ValueError("Expected a base table after FROM/JOIN")
        table = values[end]
        end += 1
        while end + 1 < len(tokens) and values[end] == "." and end + 1 in identifiers:
            table = values[end + 1]
            end += 2
        alias = table
        if end < len(tokens) and tokens[end] == ("word", "as"):
            end += 1
            if end not in identifiers:
                raise ValueError("Missing table alias after AS")
            alias, end = values[end], end + 1
        elif end in identifiers and (tokens[end][0] == "quoted" or values[end] not in SQL_ATTRIBUTE_KEYWORDS):
            alias, end = values[end], end + 1
        if table not in schema or alias in aliases:
            raise ValueError(f"Unknown table or duplicate alias: {table} AS {alias}")
        aliases[alias] = schema[table]
        consumed.update(range(index + 1, end))
    if not aliases:
        raise ValueError("No base tables found in query")
    for index, token in enumerate(tokens[:-1]):
        if token == ("word", "as") and index + 1 not in consumed:
            output_aliases.add(values[index + 1])
            consumed.add(index + 1)
    columns = set(scan_columns)
    for index in sorted(identifiers - consumed):
        if index in consumed or index + 2 >= len(tokens) or values[index + 1] != ".":
            continue
        alias, column = values[index], values[index + 2]
        if alias not in aliases or (column != "*" and column not in aliases[alias]):
            raise ValueError(f"Unresolved column reference: {alias}.{column}")
        if column == "*":
            columns.update(f"{alias}.{name}" for name in aliases[alias])
        else:
            columns.add(f"{alias}.{column}")
        consumed.update((index, index + 1, index + 2))
    # Only a standalone SELECT item is a wildcard, never COUNT(*) or multiplication.
    projection_end = tokens.index(("word", "from"))
    depth, start = 0, 1
    if tokens[start] == ("word", "distinct"):
        start += 1
    for index in range(start, projection_end + 1):
        value = values[index]
        if index == projection_end or (value == "," and depth == 0):
            if values[start:index] == ["*"]:
                columns.update(f"{alias}.{column}" for alias, names in aliases.items() for column in names)
            start = index + 1
        elif value == "(":
            depth += 1
        elif value == ")":
            depth -= 1
    for index in sorted(identifiers - consumed):
        kind, name = tokens[index]
        if (kind == "word" and name in SQL_ATTRIBUTE_KEYWORDS) or (
                index + 1 < len(tokens) and values[index + 1] == "("):
            continue
        matches = [alias for alias, names in aliases.items() if name in names]
        if len(matches) == 1:
            columns.add(f"{matches[0]}.{name}")
        elif not matches and name in output_aliases:
            continue
        else:
            raise ValueError(f"Ambiguous or unresolved column: {name}")
    return sorted(columns)


def query_attributes(row: pd.Series, catalogs: dict) -> dict:
    path = query_sql_path(row)
    sql = path.read_text(encoding="utf-8")
    family = normalize_family(row["family"])
    if family not in catalogs:
        catalogs[family] = database_columns(family)
    catalog = catalogs[family]
    columns = participating_columns(sql, catalog["tables"])
    return {"attribute_count": len(columns), "attributes": columns,
            "attribute_sql_path": str(path.resolve()), "attribute_sql_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "attribute_database": catalog["database"],
            "attribute_schema_sha256": hashlib.sha256(json.dumps(catalog["tables"], sort_keys=True).encode()).hexdigest()}


def representatives(frame: pd.DataFrame, detail: pd.DataFrame, limit: int) -> list[dict]:
    """Select complete measured profiles by family/shape/OFF ranks, never speed-up."""
    selected = frame.copy().reset_index(drop=True)
    selected = selected.loc[detail["valid_timing"].to_numpy()].copy()
    missing = pd.Series(float("nan"), index=selected.index)
    for column in ("optimizer_duckdb_total_s", "optimizer_outeryan_total_s"):
        selected[column] = pd.to_numeric(selected.get(column, missing), errors="coerce")
    complete = selected.get("optimizer_profile_status", pd.Series("", index=selected.index)).fillna("").str.upper().eq("OK")
    for column in ("optimizer_duckdb_total_s", "optimizer_outeryan_total_s"):
        complete &= selected[column].map(lambda value: math.isfinite(value) and value > 0)
    keys = query_identity_columns(selected)
    eligible = set(selected.loc[complete, keys].itertuples(index=False, name=None))
    # Use the full population for stable short IDs shared with the phase figure.
    sample = representative_runtime_rows(frame, limit=limit, scope="outeryan",
                                              eligible_queries=eligible, identity_columns=keys)
    result, catalogs = [], {}
    for _, row in sample.iterrows():
        off, on = float(row["tm_off"]), float(row["tm_on"])
        off_opt, on_opt = float(row["optimizer_duckdb_total_s"]), float(row["optimizer_outeryan_total_s"])
        record = {column: row[column] for column in (
            "short_query", "query", "workload_category", "source_run", "source_csv",
            "sql_path", "relation_count", "optimizer_timed_samples",
        ) if column in row}
        record.update({"family": normalize_family(row["family"]),
                       "relation_count": row.get("csv_relation_count", row.get("relation_count")),
                       "duckdb_s": off, "outeryan_s": on,
                       "duckdb_optimizer_ms": 1000 * off_opt, "outeryan_optimizer_ms": 1000 * on_opt,
                       "duckdb_optimizer_percent": 100 * off_opt / off,
                       "outeryan_optimizer_percent": 100 * on_opt / on})
        record.update(query_attributes(row, catalogs))
        result.append(record)
    return json.loads(pd.DataFrame(result).to_json(orient="records", double_precision=15))


def build_report_metadata(frame: pd.DataFrame, report: dict, limit: int = 3) -> dict:
    detail = prepare_queries(frame, "tm")
    measured = detail.loc[detail["valid_timing"]]
    eligible = detail.loc[detail["valid_speedup"]]
    selected = eligible.loc[eligible["selected_plan"].eq("OUTERYAN")]
    phases = report["phase_profiles"]
    phase_groups = {normalize_family(row["family"]): row for row in phases["groups"]
                    if row["scope"] in ("overall", "benchmark")}
    return {
        "schema_version": 3, "run": report["run"], "timing_threads": report["timing_threads"],
        "sources": report["sources"],
        "runtime_population": "measured",
        "headline_population": "measured_outeryan_selected",
        "corpus": composition(frame.loc[detail["valid_timing"].to_numpy()]),
        "input_corpus": composition(frame), "coverage": summarize(detail)["counts"],
        "timeouts": report["timeouts"],
        "runtime": {"all": family_summaries(eligible), "outeryan_selected": family_summaries(selected)},
        "measured_runtime": family_summaries(measured),
        "phase": [{"family": family, **phase_groups.get("all" if family == "All" else family, {})}
                  for family in FAMILIES],
        "representatives": representatives(frame, detail, limit),
        "strata": [{"dimension": dimension, "value": str(value), **summarize(rows)}
                   for dimension in DIMENSIONS if dimension in selected
                   for value, rows in selected.groupby(dimension, dropna=False, sort=True)],
        "method": {
            **report["method"],
            "corpus": "Main corpus counts use eligible complete measured pairs; raw deduplicated input counts are retained separately as input_corpus. " + runtime_filter_description(),
            "phase_percent": "100 * sum(phase operator CPU seconds) / sum(profile CPU seconds) over every eligible complete selected profile, not a representative sample or wall-time share",
            "optimization_percent": "100 * optimizer_ENGINE_total_s / tm_ENGINE, calculated separately for DuckDB/OFF and OuterYan/ON; optimizer times come from separate profiles",
            "representatives": f"Up to {limit} per family, measured OuterYan-selected queries with complete paired optimizer totals; shape quotas then evenly spaced OFF-runtime ranks; no ranking by speed-up",
            "attributes": "Count distinct (relation alias, column name) references across SELECT/JOIN/WHERE/GROUP BY/HAVING/ORDER BY. Expand projection stars using read-only database catalog metadata; COUNT(*) itself adds no column. Self-join aliases are distinct. SQL path/hash, catalog hash and full column list accompany every representative",
            "relations": "Use the original CSV relation_count when present, preserving it separately from the plot's SQL-based relation-count normalization",
            "manifest": "Current corpus manifests supply classification only; original CSV supplies every measured quantity. Missing manifest fields are unspecified; graph topology and input-tree shape are distinct",
        },
    }

















def write_report_metadata(output_directory: Path, frame: pd.DataFrame, sources: list[str],
                          limit: int = 3, report: dict | None = None) -> dict:
    """Write numerical metadata only; manuscript text and LaTeX are not outputs."""
    report = report or write_statistics(output_directory, frame, "tm", sources)
    metadata = build_report_metadata(frame, report, limit)
    manifests = [SCRIPT_DIR / "outerjoin_benchmark" / "benchmark" / name
                 for name in ("manifest.csv", "aliases.csv")]
    metadata["manifests"] = [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                             for path in manifests if path.exists()]
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "report_metadata.json").write_text(
        json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return metadata


# ---- Harness statistics interface (no Matplotlib required) --------------------

def statistics_main(argv: list[str] | None = None) -> int:
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
    combined = deduplicate_sql_results(enrich(combined, args.run))
    if args.combined_csv is not None:
        args.combined_csv.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(args.combined_csv, index=False)
    statistics_frame = combined.copy()
    statistics_frame["run"] = args.run
    write_statistics(args.output_dir, statistics_frame, args.metric, args.sources)
    return 0


def result_directories(frame: pd.DataFrame, output_dir: Path | None = None,
                       group_by: str = "date") -> dict[str, Path]:
    """Use one date directory; split thread settings/batches before writing."""
    runs = list(dict.fromkeys(frame["run"]))
    counts = Counter(run[:8] for run in runs)
    directories = {}
    for run in runs:
        if output_dir is not None:
            target = output_dir.expanduser().resolve()
            if len(runs) > 1:
                target /= run
        else:
            date = run[:8]
            if not re.fullmatch(r"\d{8}", date):
                raise ValueError("CSV group has no date; supply --output-dir for custom inputs")
            target = DEFAULT_OUTPUT_ROOT / date
            if group_by == "run":
                target /= run
            elif counts[date] > 1:
                target /= run[9:]
        directories[run] = target
    return directories


def write_result_figures(output_dir: Path, population: pd.DataFrame, run: str,
                         phase_samples: int = REPRESENTATIVE_QUERIES_PER_FAMILY) -> None:
    _load_plotting()
    measured = timed(population, "tm")
    with PdfPages(output_dir / "overview.pdf") as pdf:
        pdf.infodict().update({"Title": "OuterYan benchmark results",
                              "Subject": "ON/OFF speed-up and phase breakdown",
                              "Author": "Anonymous"})
        page_summary(pdf, measured, run)
        page_shape_relations(pdf, measured, run)
        page_speedup_scatter(pdf, population, run, "tm")
        phase_frame, notice = phase_source(population, None)
        _, phases = paired_representative_samples(population, phase_frame, phase_samples, "outeryan")
        page_phase(pdf, phases, run, notice, preselected=True)
    write_standalone_runtime_figures(output_dir, population, run, "tm", phase_samples)


def write_result_bundle(output_dir: Path, population: pd.DataFrame, *, group_by: str = "date",
                        representatives: int = 3, phase_samples: int = REPRESENTATIVE_QUERIES_PER_FAMILY) -> dict:
    """Write all outputs from the same full, deduplicated cohort exactly once."""
    sources = sorted(population["source_csv"].unique())
    report = write_statistics(output_dir, population, "tm", sources)
    metadata = write_report_metadata(output_dir, population, sources, representatives, report)
    run = str(population["run"].iloc[0])
    write_result_figures(output_dir, population, run, phase_samples)
    selection_columns = list(dict.fromkeys(query_identity_columns(population) + [
        column for column in ("query", "family", "workload_category", "original_query",
                              "original_workload_category", "original_sql_path", "source_run", "source_csv")
        if column in population]))
    (output_dir / "plot_selection.json").write_text(json.dumps({
        "group_by": group_by, "group": run,
        "runtime_filter": runtime_filter_description() + "; exclude untimed fallbacks; speed-up summaries use OuterYan-selected plans",
        "both_runtimes_below_1s": int(below_runtime_threshold(population).sum()),
        "deduplication": "latest observation per execution family and normalized SQL; includes failures; preserves literals, join kinds and grouping; unresolved SQL stays separate",
        "workloads": population["workload_category"].value_counts().to_dict(),
        "source_runs": population["source_run"].value_counts().to_dict(),
        "queries": json.loads(population[selection_columns].to_json(orient="records")),
    }, indent=2) + "\n", encoding="utf-8")
    return metadata


def main(argv: list[str] | None = None) -> int:
    global MIN_RUNTIME_SECONDS
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--statistics-only" in arguments:
        # The benchmark runner keeps its batch-specific output directory and
        # raw CSV schema. Do not add a Matplotlib requirement to server runs.
        arguments.remove("--statistics-only")
        return statistics_main(arguments)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="*", help="original CSV files or glob patterns; defaults to auto_test/results/experiment_onoff_*.csv")
    parser.add_argument("--date", help="experiment date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--output-dir", type=Path,
                        help="optional override; default: auto_test/results/plots/DATE/")
    parser.add_argument("--group-by", choices=("date", "run"), default="date",
                        help="combine same-date versions (default), or keep experiment batches separate")
    parser.add_argument("--representatives-per-benchmark", type=int, default=3,
                        help="optimizer-table representatives per family (default: 3)")
    parser.add_argument("--phase-samples-per-benchmark", type=int, default=REPRESENTATIVE_QUERIES_PER_FAMILY,
                        help="phase-figure representatives per family (default: 15)")
    parser.add_argument("--exclude-selectivity-stress", action="store_true",
                        help="exclude the wide-range ablation from all generated results")
    parser.add_argument("--include-subsecond", action="store_true",
                        help="retain measured pairs even when both runtimes are below 1 s (review mode)")
    parser.add_argument("--statistics-only", action="store_true",
                        help="internal harness mode: requires --run and --output-dir; statistics only")
    args = parser.parse_args(arguments)
    if args.representatives_per_benchmark < 1 or args.phase_samples_per_benchmark < 1:
        parser.error("representative and phase sample counts must be positive")
    date = args.date.replace("-", "") if args.date else None
    if date:
        try:
            if not re.fullmatch(r"\d{8}", date):
                raise ValueError()
            datetime.strptime(date, "%Y%m%d")
        except ValueError:
            parser.error("--date must be a valid YYYYMMDD or YYYY-MM-DD date")
    paths = resolve_inputs(args.csv or DEFAULT_INPUTS, Path.cwd() if args.csv else SCRIPT_DIR)
    if not paths:
        parser.error("No input CSV files found")
    frame = load(paths, group_by=args.group_by, date=date)
    if args.exclude_selectivity_stress:
        frame = frame.loc[~frame.get("selectivity_stress", pd.Series(False, index=frame.index)).fillna(False)]
    if frame.empty:
        parser.error("No matching query instances")
    try:
        directories = result_directories(frame, args.output_dir, args.group_by)
    except ValueError as error:
        parser.error(str(error))
    previous_threshold = MIN_RUNTIME_SECONDS
    try:
        MIN_RUNTIME_SECONDS = 0.0 if args.include_subsecond else 1.0
        for run, output in directories.items():
            population = frame.loc[frame["run"].eq(run)].copy()
            metadata = write_result_bundle(output, population, group_by=args.group_by,
                                        representatives=args.representatives_per_benchmark,
                                        phase_samples=args.phase_samples_per_benchmark)
            print(f"Results: {output} ({metadata['corpus']['total']} valid instances from {metadata['input_corpus']['total']} input instances, "
                  f"{metadata['coverage']['measured']} retained measured pairs)")
    finally:
        MIN_RUNTIME_SECONDS = previous_threshold
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
