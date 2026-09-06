#!/usr/bin/env python3
"""Render OuterYan ON/OFF results as one multi-page benchmark PDF.

CSV files that share a ``YYYYMMDD_HHMMSS`` timestamp are one logical run.
Consequently, historical ``core``, ``custom``, and ``industry_inspired`` CSVs
from the same invocation are merged before plotting. Attempts files fill rows
missing from the final CSV; final rows win duplicates.

The PDF contains summary and shape/relation-count pages, compact per-query
runtime views for all queries, separate JOB and other-benchmark OuterYan-selected
runtime comparisons with both thread settings, and one vertical phase-breakdown
figure shared by every family. There is intentionally no
kernel-speedup view.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


C_T1 = "#4C72B0"
C_TM = "#DD8452"
FAMILY_ORDER = ["graph", "TPC-H", "TPC-DS", "JOB"]
TOPOLOGY_ORDER = ["left-deep", "right-deep", "bushy", "star", "aggregate", "industry"]
CLASS_ORDER = ["derived", "industry", "custom", "legacy"]
FAMILY_CODES = {"graph": "G", "TPC-H": "H", "TPC-DS": "D", "JOB": "J"}
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
QUERY_CODE_KEY = (
    "G=graph, H=TPC-H, D=TPC-DS, J=JOB; LD=left-deep, RD=right-deep, "
    "B=bushy, S=star, A=aggregate, I=industry, O=other"
)
RUNTIME_SERIES = [
    ("Single-thread: DuckDB (OFF)", "t1_off", "#A4BEDF"),
    ("Single-thread: OuterYan (ON)", "t1_on", "#6B9AC7"),
    ("Multi-thread: DuckDB (OFF)", "tm_off", "#EFC69E"),
    ("Multi-thread: OuterYan (ON)", "tm_on", "#E59C6D"),
]
PHASES = [
    ("Round 1", "profile_round1_operator_s", "profile_round1_ratio", "#4C72B0"),
    ("Round 2", "profile_round2_operator_s", "profile_round2_ratio", "#55A868"),
    ("Round 3", "profile_round3_operator_s", "profile_round3_ratio", "#DD8452"),
    ("Other", "profile_other_elapsed_s", "profile_other_ratio", "#999999"),
]
OUTERYAN_TOTAL_LABEL = "Total Time"
OUTERYAN_TOTAL_COLOR = "#E2B448"

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUTS = ["results/experiment_onoff_*.csv"]
DEFAULT_OUTPUT = SCRIPT_DIR / "results" / "plots" / "outeryan_benchmark_figures.pdf"


def gmean(values: pd.Series | np.ndarray) -> float:
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data) & (data > 0)]
    return float(np.exp(np.mean(np.log(data)))) if data.size else np.nan


def strip_provenance_prefix(query: str) -> str:
    return re.sub(
        r"^(?:derived|industry|industrywin|legacywin|custom)__",
        "",
        str(query),
        flags=re.IGNORECASE,
    )


def class_from_query(query: str) -> str | None:
    prefix = str(query).split("__", 1)[0].lower() if "__" in str(query) else ""
    return {
        "derived": "derived",
        "industry": "industry",
        # Compatibility for result files generated before the two-prefix merge.
        "industrywin": "industry",
        "legacywin": "derived",
        "custom": "custom",
    }.get(prefix)


def family_from_query(query: str) -> str:
    query = strip_provenance_prefix(query).lower()
    if query.startswith(("oy_th", "ojb_tpch", "ojb_sqlstorm_tpch")):
        return "TPC-H"
    if query.startswith(("oy_ds", "ojb_tpcds", "ojb_sqlstorm_tpcds")):
        return "TPC-DS"
    if query.startswith(("oy_jb", "ojb_job", "ojb_sqlstorm_job")):
        return "JOB"
    return "graph"


def topology_from_query(query: str) -> str:
    query = strip_provenance_prefix(query).lower()
    if re.search(r"_(?:ldmx|ldu[lrfi]|alt)$", query):
        return "left-deep"
    if re.search(r"_(?:rdmx|rdax|rdu[lrfi])$", query):
        return "right-deep"
    if re.search(r"_(?:bmx|bdmx)$", query):
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
    stem = re.sub(r"^experiment_onoff_", "", stem)
    match = re.search(r"(?:^|_)(\d{8}_\d{6})$", stem)
    if not match:
        return stem, source_kind, "custom"
    run = match.group(1)
    label = stem[: match.start()].rstrip("_") or "legacy"
    return run, source_kind, label


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
        "relation_count", "profile_threads", "profile_total_time_s", "profile_cpu_time_s",
        *(seconds for _, seconds, _, _ in PHASES),
        *(ratio for _, _, ratio, _ in PHASES),
    ]
    for column in numeric:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    inferred_family = frame["query"].map(family_from_query)
    if "family" in frame:
        reported = frame["family"].astype("string").str.strip().str.lower().map(
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
        corpus_root = SCRIPT_DIR / "outerjoin_query"

        def relation_count_from_sql_path(relative_path: object) -> float:
            if not isinstance(relative_path, str) or not relative_path:
                return np.nan
            path = Path(relative_path)
            if path.is_absolute() or ".." in path.parts:
                return np.nan
            try:
                sql = (corpus_root / path).read_text(encoding="utf-8")
            except OSError:
                return np.nan
            sql = re.sub(r"--[^\n]*", "", sql)
            sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
            count = len(re.findall(r"\b(?:FROM|JOIN)\b", sql, flags=re.IGNORECASE))
            return float(count) if count > 0 else np.nan

        sql_relations = frame["sql_path"].map(relation_count_from_sql_path)
    if "relation_count" in frame:
        valid = frame["relation_count"].where(
            frame["relation_count"].gt(0)
            & frame["relation_count"].eq(np.floor(frame["relation_count"]))
        )
        frame["relation_count"] = sql_relations.fillna(valid).fillna(fallback_relations)
    else:
        frame["relation_count"] = sql_relations.fillna(fallback_relations)

    frame["display_query"] = frame["query"].astype(str)
    return frame


def load(paths: list[str]) -> pd.DataFrame:
    grouped: dict[str, list[pd.DataFrame]] = {}
    for source_order, path in enumerate(paths):
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
        raw["__plot_source_priority"] = 0 if source_kind == "attempts" else 1
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
    order_columns = ["__plot_source_priority", "__plot_source_order", "__plot_row_order"]
    for run, sources in grouped.items():
        combined = pd.concat(sources, ignore_index=True, sort=False)
        reported_family = combined.get(
            "family", pd.Series("", index=combined.index, dtype="object")
        ).astype("string").str.strip().str.lower()
        merge_family = reported_family.where(
            reported_family.ne(""), combined["query"].map(family_from_query).str.lower()
        ).replace({"tpch": "tpc-h", "tpcds": "tpc-ds"})
        combined["__plot_merge_family"] = merge_family
        combined = combined.sort_values(order_columns, kind="stable")
        keys = ["__plot_merge_family", "query"]
        duplicate_count = int(combined.duplicated(keys, keep="last").sum())
        merged = combined.drop_duplicates(keys, keep="last").sort_values(
            ["__plot_row_order", "__plot_source_priority", "__plot_source_order"], kind="stable"
        )
        merged = merged.drop(columns=order_columns + ["__plot_merge_family"])
        frames.append(enrich(merged, run))
        print(
            f"  unified run {run}: {len(combined)} component rows -> "
            f"{len(merged)} benchmark queries ({duplicate_count} duplicates removed)"
        )
    return pd.concat(frames, ignore_index=True)


def timed(frame: pd.DataFrame) -> pd.DataFrame:
    correct = frame.get("correct", "TRUE").astype(str).str.upper().eq("TRUE")
    measured = frame["t1_speedup"].notna() | frame["tm_speedup"].notna()
    return frame.loc[correct & measured].copy()


def grouped_box(ax: plt.Axes, frame: pd.DataFrame, column: str, order: list[str], title: str) -> None:
    order = [value for value in order if value in set(frame[column].dropna())]
    if not order:
        ax.set_visible(False)
        return
    width = 0.38
    rng = np.random.default_rng(0)
    for series_index, (metric, color) in enumerate((("t1_speedup", C_T1), ("tm_speedup", C_TM))):
        data = [frame.loc[frame[column].eq(value), metric].dropna().to_numpy() for value in order]
        positions = [index + (series_index - 0.5) * width for index in range(len(order))]
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
        handles=[Patch(facecolor=C_T1, edgecolor="none", alpha=0.62, label="T1"),
                 Patch(facecolor=C_TM, edgecolor="none", alpha=0.62, label="TM")], fontsize=8
    )


def save_page(pdf: PdfPages, figure: plt.Figure) -> None:
    pdf.savefig(figure, bbox_inches="tight")
    plt.close(figure)


def tighten_mosaic(figure: plt.Figure, rect: tuple[float, float, float, float]) -> None:
    """Apply tight layout while tolerating the intentional row-spanning JOB axis."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="This figure includes Axes that are not compatible with tight_layout",
        )
        figure.tight_layout(rect=rect)


def page_summary(pdf: PdfPages, frame: pd.DataFrame, run: str) -> None:
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
    """Assign stable family-shape indices such as H-RD-01 and J-B-03."""
    labeled = frame.copy()
    labeled["_family_code"] = labeled["family"].map(FAMILY_CODES).fillna("X")
    labeled["_shape_code"] = labeled["topology"].map(TOPOLOGY_CODES).fillna("O")
    stable = labeled.sort_values(["family", "topology", "query"], kind="stable")
    stable["_shape_index"] = stable.groupby(
        ["family", "_shape_code"], sort=False
    ).cumcount() + 1
    labeled["_shape_index"] = stable["_shape_index"].reindex(labeled.index)
    labeled["short_query"] = [
        f"{family}-{shape}-{index:02d}"
        for family, shape, index in zip(
            labeled["_family_code"], labeled["_shape_code"], labeled["_shape_index"]
        )
    ]
    return labeled


def sample_phase_queries(frame: pd.DataFrame, limit: int = PHASE_SAMPLE_PER_FAMILY) -> pd.DataFrame:
    """Select deterministic, evenly spaced rows from each family and runtime range."""
    sampled: list[pd.DataFrame] = []
    family_sizes = frame["family"].value_counts().to_dict()
    for family in FAMILY_ORDER:
        family_rows = frame.loc[frame["family"].eq(family)].sort_values(
            ["topology", "profile_total_time_s", "query"], kind="stable"
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


def grouped_query_positions(
    frame: pd.DataFrame, gap: float = 1.75
) -> tuple[pd.DataFrame, list[tuple[str, float, float, int, int]]]:
    """Order query bars by benchmark and shape, leaving gaps for group subtitles."""
    topology_rank = {name: index for index, name in enumerate(TOPOLOGY_ORDER + ["other"])}
    parts: list[pd.DataFrame] = []
    groups: list[tuple[str, float, float, int, int]] = []
    cursor = 0.0
    for family in FAMILY_ORDER:
        family_rows = frame.loc[frame["family"].eq(family)].copy()
        if family_rows.empty:
            continue
        family_rows["_topology_rank"] = family_rows["topology"].map(topology_rank).fillna(99)
        family_rows = family_rows.sort_values(
            ["_topology_rank", "short_query"], kind="stable"
        )
        positions = cursor + np.arange(len(family_rows), dtype=float)
        family_rows["_x"] = positions
        available = int(family_rows.get("_family_available", pd.Series(len(family_rows))).iloc[0])
        groups.append((family, float(positions[0]), float(positions[-1]), len(family_rows), available))
        parts.append(family_rows)
        cursor = float(positions[-1] + 1.0 + gap)
    return pd.concat(parts, ignore_index=False), groups


def add_benchmark_subtitles(
    ax: plt.Axes, groups: list[tuple[str, float, float, int, int]]
) -> None:
    for index, (family, left, right, shown, available) in enumerate(groups):
        count = f"n={shown}" if shown == available else f"n={shown} of {available}"
        ax.text(
            (left + right) / 2.0, 1.015, f"{family} ({count})",
            transform=ax.get_xaxis_transform(), ha="center", va="bottom",
            fontsize=13, fontweight="semibold", clip_on=False,
        )
        if index:
            previous_right = groups[index - 1][2]
            ax.axvline((previous_right + left) / 2.0, color="0.78", linewidth=0.7)


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


def selected_runtime_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep OuterYan-selected queries with all four finite, positive timings."""
    plans = frame.get("selected_plan", pd.Series("", index=frame.index)).astype(str).str.upper()
    sub = frame.loc[plans.eq("OUTERYAN")].copy()
    complete = pd.Series(True, index=sub.index)
    for _, column, _ in RUNTIME_SERIES:
        values = pd.to_numeric(
            sub.get(column, pd.Series(np.nan, index=sub.index)), errors="coerce"
        )
        valid = np.isfinite(values) & values.gt(0)
        sub[column] = values.where(valid)
        complete &= valid
    return sub.loc[complete].copy()


def page_selected_runtime_bars(pdf: PdfPages, frame: pd.DataFrame) -> None:
    sub, groups = grouped_query_positions(frame)
    x = sub["_x"].to_numpy(float)
    values = sub[[column for _, column, _ in RUNTIME_SERIES]].to_numpy(float)
    positive = values[np.isfinite(values) & (values > 0)]
    floor = 10 ** (np.log10(positive.min()) - 0.25)
    width = min(29.0, max(17.0, 4.0 + 0.44 * len(sub)))
    figure, ax = plt.subplots(figsize=(width, 7.8))
    bar_width = 0.18
    # A little extra space between thread settings makes each OFF/ON pair clear.
    offsets = (-0.30, -0.12, 0.12, 0.30)
    for offset, (label, column, color) in zip(offsets, RUNTIME_SERIES):
        heights = sub[column].to_numpy(float)
        ax.bar(
            x + offset, heights - floor, bottom=floor,
            width=bar_width, color=color, edgecolor="none", label=label,
        )
    ax.set_yscale("log")
    ax.set_ylim(floor, positive.max() * 1.35)
    ax.set_xlim(x.min() - 0.8, x.max() + 0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(sub["short_query"], rotation=90, ha="center", fontsize=11)
    ax.tick_params(axis="y", labelsize=12)
    ax.set_ylabel("Wall-clock time (seconds, log)", fontsize=14)
    ax.set_xlabel("Query", fontsize=14, labelpad=8)
    ax.grid(axis="y", which="major", color="0.88", linewidth=0.6)
    ax.grid(axis="y", which="minor", color="0.95", linewidth=0.4)
    ax.set_axisbelow(True)
    add_benchmark_subtitles(ax, groups)
    handles, labels = ax.get_legend_handles_labels()
    figure.legend(
        handles, labels, loc="upper center", bbox_to_anchor=(0.52, 0.911),
        ncol=len(handles), frameon=False, fontsize=11,
    )
    figure.suptitle("Running time Comparison", fontsize=18, y=0.955)
    figure.text(
        0.52, 0.050, QUERY_CODE_KEY, ha="center", va="bottom", fontsize=10.5,
    )
    figure.subplots_adjust(left=0.055, right=0.99, bottom=0.245, top=0.81)
    save_page(pdf, figure)


def page_runtime(
    pdf: PdfPages, frame: pd.DataFrame, run: str, metric: str, selected_only: bool
) -> None:
    if selected_only:
        plans = frame.get("selected_plan", pd.Series("", index=frame.index)).astype(str).str.upper()
        # Assign labels before excluding incomplete queries so their IDs do not shift.
        labeled = add_short_query_labels(frame.loc[plans.eq("OUTERYAN")])
        sub = selected_runtime_rows(labeled)
        if sub.empty:
            print(f"  runtime figure omitted for {run}: no complete OuterYan-selected timings")
            return
        is_job = sub["family"].eq("JOB")
        for group in (sub.loc[~is_job], sub.loc[is_job]):
            if not group.empty:
                page_selected_runtime_bars(pdf, group)
        return
    sub = positive_runtime_rows(frame, metric)
    if sub.empty:
        print(f"  runtime figure omitted for {run}: no timed queries")
        return
    figure, axes = benchmark_mosaic(
        sub, row_inches=0.115, minimum_height=8.0,
    )
    for family, ax in axes.items():
        family_rows = sub.loc[sub["family"].eq(family)].copy()
        plot_runtime_axis(ax, family_rows, metric, family, show_plan=True)
    figure.suptitle("Runtime - all correct and timed queries", fontsize=14, y=0.995)
    figure.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="none", color=C_T1,
                   markersize=5, label="OuterYan OFF (DuckDB)"),
            Line2D([], [], marker="o", linestyle="none", color=C_TM,
                   markersize=5, label="OuterYan enabled (ON)"),
        ],
        loc="upper center", ncol=2, fontsize=8, frameon=False,
        bbox_to_anchor=(0.5, 0.975),
    )
    tighten_mosaic(figure, (0.01, 0.01, 0.99, 0.945))
    save_page(pdf, figure)


def complete_phase_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    seconds_columns = [seconds for _, seconds, _, _ in PHASES]
    ratio_columns = [ratio for _, _, ratio, _ in PHASES]
    required = seconds_columns + ratio_columns + ["profile_total_time_s"]
    if not set(required).issubset(frame.columns):
        return frame.iloc[0:0].copy(), 0
    plans = frame.get("selected_plan", pd.Series("", index=frame.index)).astype(str).str.upper()
    selected = frame.loc[plans.eq("OUTERYAN")].copy()
    if selected.empty:
        return selected, 0
    for column in required + ["profile_threads", "profile_cpu_time_s"]:
        if column in selected:
            selected[column] = pd.to_numeric(selected[column], errors="coerce")
    seconds = selected[seconds_columns]
    ratios = selected[ratio_columns]
    total_time = selected["profile_total_time_s"]
    cpu_time = selected.get("profile_cpu_time_s", total_time).where(
        lambda value: np.isfinite(value) & value.gt(0), total_time
    )
    complete = (
        np.isfinite(seconds).all(axis=1)
        & seconds.ge(0).all(axis=1)
        & np.isfinite(ratios).all(axis=1)
        & ratios.ge(0).all(axis=1)
        & ratios.le(1).all(axis=1)
        & np.isfinite(total_time)
        & total_time.gt(0)
        & np.isfinite(cpu_time)
        & cpu_time.gt(0)
        & np.isclose(seconds.sum(axis=1), cpu_time, rtol=1e-6, atol=1e-9)
        & ratios.sum(axis=1).sub(1.0).abs().le(1e-6)
        & np.isclose(
            ratios.to_numpy(float), seconds.div(cpu_time, axis=0).to_numpy(float), atol=1e-6
        ).all(axis=1)
    )
    selected["_profile_cpu_time"] = cpu_time
    return selected.loc[complete].copy(), int((~complete).sum())


def page_phase(pdf: PdfPages, frame: pd.DataFrame, run: str) -> None:
    sub, skipped = complete_phase_rows(frame)
    if sub.empty:
        print(f"  phase breakdown omitted for {run}: no complete selected profiles")
        return
    sub = add_short_query_labels(sub)
    sub = sample_phase_queries(sub)
    sub, groups = grouped_query_positions(sub)
    seconds_columns = [seconds for _, seconds, _, _ in PHASES]
    totals = sub["profile_total_time_s"].to_numpy(float)
    phase_values = sub[seconds_columns].to_numpy(float)
    positive = np.concatenate([phase_values[phase_values > 0], totals])
    floor = 10 ** (np.log10(positive.min()) - 0.25)
    x = sub["_x"].to_numpy(float)
    width = min(30.0, max(19.0, 4.0 + 0.44 * len(sub)))
    figure, ax = plt.subplots(figsize=(width, 8.2))
    bar_width = 0.16
    series = [
        (label, seconds, color) for label, seconds, _, color in PHASES
    ] + [(OUTERYAN_TOTAL_LABEL, "profile_total_time_s", OUTERYAN_TOTAL_COLOR)]
    offsets = (np.arange(len(series)) - (len(series) - 1) / 2.0) * bar_width
    for offset, (label, column, color) in zip(offsets, series):
        values = sub[column].to_numpy(float)
        present = values > 0
        ax.bar(
            x[present] + offset, values[present] - floor, bottom=floor,
            width=bar_width, color=color, edgecolor="none", label=label,
        )
    ax.set_yscale("log")
    ax.set_ylim(floor, positive.max() * 1.45)
    ax.set_xlim(x.min() - 0.9, x.max() + 0.9)
    ax.set_xticks(x)
    ax.set_xticklabels(sub["short_query"], rotation=90, ha="center", fontsize=11)
    ax.tick_params(axis="y", labelsize=12)
    ax.set_ylabel("Time (seconds, log)", fontsize=14)
    ax.set_xlabel("Query", fontsize=14, labelpad=8)
    ax.grid(axis="y", which="major", color="0.88", linewidth=0.6)
    ax.grid(axis="y", which="minor", color="0.95", linewidth=0.4)
    ax.set_axisbelow(True)
    add_benchmark_subtitles(ax, groups)
    if skipped:
        print(f"  phase breakdown for {run}: {skipped} incomplete selected profiles omitted")
    figure.suptitle(
        "OuterYan Execution Time Details", fontsize=18, y=0.955,
    )
    phase_handles = [
        Patch(facecolor=color, edgecolor="none", label=label)
        for label, _, _, color in PHASES
    ]
    phase_handles.append(
        Patch(facecolor=OUTERYAN_TOTAL_COLOR, edgecolor="none", label=OUTERYAN_TOTAL_LABEL)
    )
    figure.legend(
        handles=phase_handles, ncol=5, fontsize=12, loc="upper center", frameon=False,
        bbox_to_anchor=(0.52, 0.906),
    )
    figure.text(
        0.52, 0.050, QUERY_CODE_KEY, ha="center", va="bottom", fontsize=10.5,
    )
    figure.subplots_adjust(left=0.05, right=0.99, bottom=0.235, top=0.815)
    save_page(pdf, figure)


def page_run_comparison(pdf: PdfPages, frame: pd.DataFrame) -> None:
    runs = list(dict.fromkeys(frame["run"]))
    if len(runs) < 2:
        return
    pivot = frame.pivot_table(
        index=["family", "query"], columns="run", values="tm_speedup", aggfunc="median"
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
    return [path for path in paths if path.lower().endswith(".csv")]


def write_standalone_runtime_figures(
    output_directory: Path, frame: pd.DataFrame, run: str, metric: str
) -> list[Path]:
    """Write all-query dots, two selected-runtime comparisons, and sampled phases."""
    output_directory.mkdir(parents=True, exist_ok=True)
    outputs = [
        ("runtime_all_queries.pdf", lambda pdf: page_runtime(pdf, frame, run, metric, False)),
        ("runtime_outeryan_queries.pdf", lambda pdf: page_runtime(
            pdf, frame.loc[~frame["family"].eq("JOB")], run, metric, True
        )),
        ("runtime_outeryan_queries_job.pdf", lambda pdf: page_runtime(
            pdf, frame.loc[frame["family"].eq("JOB")], run, metric, True
        )),
        ("phase_breakdown_outeryan.pdf", lambda pdf: page_phase(pdf, frame, run)),
    ]
    paths: list[Path] = []
    for filename, draw in outputs:
        path = output_directory / filename
        with PdfPages(path) as pdf:
            draw(pdf)
        paths.append(path)
        print(f"  wrote standalone figure: {path}")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="*", help="experiment_onoff CSV files")
    parser.add_argument(
        "-o", "--output", default=str(DEFAULT_OUTPUT),
        help="single output PDF (default: auto_test/results/plots/outeryan_benchmark_figures.pdf)"
    )
    parser.add_argument(
        "--split-output-dir",
        help="also write runtime_all_queries.pdf, runtime_outeryan_queries.pdf (non-JOB), "
             "runtime_outeryan_queries_job.pdf, and phase_breakdown_outeryan.pdf; "
             "multiple runs receive timestamp subdirectories",
    )
    parser.add_argument(
        "--metric", choices=["t1", "tm"], default="tm",
        help="thread setting for all-query dots; selected-runtime bars always show both",
    )
    args = parser.parse_args()

    paths = resolve_inputs(
        args.csv or DEFAULT_INPUTS,
        Path.cwd() if args.csv else SCRIPT_DIR,
    )
    if not paths:
        raise SystemExit("No input CSV files found.")
    output = Path(os.path.expanduser(args.output))
    if not output.is_absolute():
        output = Path.cwd() / output
    if output.suffix.lower() != ".pdf":
        output = output / "outeryan_benchmark_figures.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)

    frame = load(paths)
    measured = timed(frame)
    print(f"\n{len(measured)} timed rows across {measured['run'].nunique()} logical run(s)")
    with PdfPages(output) as pdf:
        metadata = pdf.infodict()
        metadata["Title"] = "OuterYan unified benchmark figures"
        metadata["Subject"] = "ON/OFF speed-up and phase breakdown"
        metadata["Author"] = "DuckYanOuter auto_test"
        for run in dict.fromkeys(frame["run"]):
            sub = measured.loc[measured["run"].eq(run)].copy()
            skipped = int(frame["run"].eq(run).sum() - len(sub))
            print(f"\n>>> unified run {run}: {len(sub)} timed, {skipped} skipped")
            page_summary(pdf, sub, run)
            page_shape_relations(pdf, sub, run)
            page_runtime(pdf, sub, run, args.metric, selected_only=False)
            page_runtime(pdf, sub, run, args.metric, selected_only=True)
            page_phase(pdf, sub, run)
        page_run_comparison(pdf, measured)
    print(f"\nwrote one PDF: {output}")

    if args.split_output_dir:
        split_root = Path(os.path.expanduser(args.split_output_dir))
        if not split_root.is_absolute():
            split_root = Path.cwd() / split_root
        runs = list(dict.fromkeys(frame["run"]))
        for run in runs:
            sub = measured.loc[measured["run"].eq(run)].copy()
            run_directory = split_root / run if len(runs) > 1 else split_root
            write_standalone_runtime_figures(run_directory, sub, run, args.metric)


if __name__ == "__main__":
    main()
