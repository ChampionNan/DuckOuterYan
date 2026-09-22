#!/usr/bin/env python3
"""Render OuterYan ON/OFF results as publication-style benchmark figures.

CSV files that share a ``YYYYMMDD_HHMMSS`` timestamp and optional thread suffix
are one logical run. The ``_t16`` and ``_t32`` configurations remain separate.
Consequently, historical ``core``, ``custom``, and ``industry_inspired`` CSVs
from the same invocation are merged before plotting. Attempts files fill rows
missing from the final CSV; final rows win duplicates.

The PDF contains summary and shape/relation-count pages, a compact two-panel
runtime comparison for all measured queries, and a representative round-time
breakdown. New runs use multi-thread timings and separate native phase profiles.
Explicit legacy phase placeholders are visibly labeled and never contribute to
current runtime statistics.

Round 1/2/3 and Other are aggregate operator CPU work. They close against
``profile_total_time_s`` (also recorded as ``profile_cpu_time_s``). Root query
latency is recorded separately as ``profile_wall_time_s``. Historical CSVs,
where ``profile_total_time_s`` meant wall time, remain supported.
"""

from __future__ import annotations

import argparse
import glob
import json
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
from matplotlib.legend_handler import HandlerTuple
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


C_T1 = "#4C72B0"
C_TM = "#DD8452"
FAMILY_ORDER = ["graph", "TPC-H", "TPC-DS", "JOB"]
FAMILY_COLORS = {
    "graph": "#7A7A7A",
    "TPC-H": "#E64B35",
    "TPC-DS": "#315EFB",
    "JOB": "#00A087",
}
REPRESENTATIVE_QUERIES_PER_FAMILY = 15
TOPOLOGY_ORDER = ["left-deep", "right-deep", "bushy", "star", "aggregate", "industry"]
CLASS_ORDER = ["derived", "industry", "selectivity stress", "JOB regression", "custom", "legacy"]
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
PHASE_GROUP_GAP = 0.62
QUERY_POINT_SIZE = 28
QUERY_POINT_ALPHA = 0.52
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
    ("Round 1 semi-joins", "profile_round1_operator_s", "profile_round1_ratio", "#3B6FB6"),
    ("Round 2 semi-joins", "profile_round2_operator_s", "profile_round2_ratio", "#5AAE61"),
    ("Round 3 real joins", "profile_round3_operator_s", "profile_round3_ratio", "#E08245"),
    ("Other operators", "profile_other_elapsed_s", "profile_other_ratio", "#A0A0A0"),
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
plt.rcParams.update(ACADEMIC_STYLE)

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUTS = ["results/experiment_onoff_*.csv"]
DEFAULT_OUTPUT = SCRIPT_DIR / "results" / "plots" / "outeryan_benchmark_figures.pdf"
STANDALONE_PNG_DPI = 300


def benchmark_provenance() -> pd.DataFrame:
    """Return auditable v1/v2 active-corpus roles keyed by emitted query id."""
    manifests = [
        SCRIPT_DIR / "outerjoin_benchmark" / "benchmark" / "manifest.csv",
        SCRIPT_DIR / "outerjoin_benchmark" / "v2" / "benchmark" / "manifest.csv",
    ]
    frames = []
    for path in manifests:
        if not path.exists():
            continue
        manifest = pd.read_csv(path)
        required = {"query_id", "source_component", "evaluation_role"}
        if not required.issubset(manifest.columns):
            continue
        frames.append(manifest[["query_id", "source_component", "evaluation_role"]])
    if not frames:
        return pd.DataFrame(
            columns=["query_id", "source_component", "evaluation_role", "workload_component"]
        )
    provenance = pd.concat(frames, ignore_index=True).drop_duplicates("query_id", keep="last")
    provenance["workload_component"] = provenance["source_component"].map(
        {"core": "structural", "industry_inspired": "evaluation"}
    ).fillna("evaluation")
    return provenance


def gmean(values: pd.Series | np.ndarray) -> float:
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data) & (data > 0)]
    return float(np.exp(np.mean(np.log(data)))) if data.size else np.nan


def strip_provenance_prefix(query: str) -> str:
    return re.sub(
        r"^(?:derived|industry|industrywin|legacywin|custom|stress|regression)__",
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
        "stress": "selectivity stress",
        "regression": "JOB regression",
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
    selectivity_suffix = (
        r"(?:_(?:sel(?:001|01|05)|stress(?:0025|005|02|10|20|50|80)))?$"
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
    stem = re.sub(r"^experiment_onoff_", "", stem)
    match = re.search(r"(?:^|_)(\d{8}_\d{6})(_t[1-9][0-9]*)?$", stem)
    if not match:
        return stem, source_kind, "custom"
    run = match.group(1) + (match.group(2) or "")
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
    provenance = benchmark_provenance().set_index("query_id")
    for column in ("source_component", "evaluation_role", "workload_component"):
        if column not in frame:
            frame[column] = frame["query"].map(provenance[column])
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
    correct = frame.get("correct", pd.Series("TRUE", index=frame.index)).astype(str).str.upper().eq("TRUE")
    missing = pd.Series(np.nan, index=frame.index)
    measured = frame.get("t1_speedup", missing).notna() | frame.get("tm_speedup", missing).notna()
    return frame.loc[correct & measured].copy()


def grouped_box(ax: plt.Axes, frame: pd.DataFrame, column: str, order: list[str], title: str) -> None:
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
    correct = frame.get("correct", pd.Series("TRUE", index=frame.index)).astype(str).str.upper().eq("TRUE")
    timeout = frame.get("note", pd.Series("", index=frame.index)).fillna("").astype(str).str.contains(
        "TIMEOUT", case=False, regex=False
    )
    sub = frame.loc[correct & ~timeout].copy()
    complete = pd.Series(True, index=sub.index)
    for _, column, _ in runtime_series(frame):
        values = pd.to_numeric(
            sub.get(column, pd.Series(np.nan, index=sub.index)), errors="coerce"
        )
        valid = np.isfinite(values) & values.gt(0)
        sub[column] = values.where(valid)
        complete &= valid
    return sub.loc[complete].copy()


def selected_runtime_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep OuterYan-selected queries with complete timings for their schema."""
    plans = frame.get("selected_plan", pd.Series("", index=frame.index)).astype(str).str.upper()
    return complete_runtime_rows(frame.loc[plans.eq("OUTERYAN")])


def representative_runtime_rows(
    frame: pd.DataFrame, limit: int = REPRESENTATIVE_QUERIES_PER_FAMILY, scope: str = "outeryan",
    eligible_queries: set[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """Per-family caps, round-robin shape quotas, then OFF-runtime quantiles.

    Eligibility requires correct, complete timings and the requested plan scope.
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
        eligible = eligible.loc[[
            (family, query) in eligible_queries for family, query in zip(eligible["family"], eligible["query"])
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
    lower, upper = float(all_values.min() - padding), float(all_values.max() + padding)
    candidates = np.asarray([0.1, 0.25, 0.5, 1, 2, 4, 10, 25, 50, 100, 250], dtype=float)
    ticks = np.log10(candidates)
    visible = (ticks >= lower) & (ticks <= upper)
    ax.set_xlim(lower, upper)
    ax.set_xticks(ticks[visible], [f"{value:g}×" for value in candidates[visible]])
    ax.set_yticks(positions, families)
    ax.invert_yaxis()
    ax.axvline(0.0, color="0.45", linewidth=0.8, zorder=1)
    ax.axvspan(lower, 0.0, color="#F7EEEE", alpha=0.35, zorder=0)
    # A restrained density-independent gradient makes larger speed-ups read as
    # progressively stronger improvements without changing the data marks.
    gradient = np.empty((2, 256, 4), dtype=float)
    gradient[:, :, :3] = np.asarray([0x78, 0xBE, 0x8C], dtype=float) / 255.0
    gradient[:, :, 3] = np.linspace(0.02, 0.13, gradient.shape[1])
    y_limits = ax.get_ylim()
    ax.imshow(
        gradient, extent=(0.0, upper, min(y_limits), max(y_limits)), origin="lower",
        aspect="auto", interpolation="bicubic", zorder=0,
    )
    ax.set_ylim(y_limits)
    ax.set_xlabel("DuckDB vs. OuterYan")
    ax.tick_params(axis="both", direction="in", top=True, right=True)
    ax.grid(axis="x", color="0.90", linewidth=0.55, zorder=0)
    ax.text(0.02, 0.97, "OuterYan slower", transform=ax.transAxes, ha="left", va="top",
            fontsize=8, color="#8A4E4E")
    ax.text(0.98, 0.97, "OuterYan faster", transform=ax.transAxes, ha="right", va="top",
            fontsize=8, color="#3E7351")


def page_speedup_scatter(pdf: PdfPages, frame: pd.DataFrame, run: str, metric: str) -> None:
    """Runtime relationship plus a compact per-benchmark speed-up distribution."""
    correct = frame.get("correct", pd.Series("TRUE", index=frame.index)).astype(str).str.upper().eq("TRUE")
    sub = positive_runtime_rows(frame.loc[correct], metric)
    if sub.empty:
        print(f"  speed-up figure omitted for {run}: no complete timings")
        return
    sub["_speedup"] = sub[f"{metric}_off"] / sub[f"{metric}_on"]
    sub = sub.loc[np.isfinite(sub["_speedup"]) & sub["_speedup"].gt(0)]
    if sub.empty:
        return
    families = [family for family in FAMILY_ORDER if sub["family"].eq(family).any()]
    off_column, on_column = f"{metric}_off", f"{metric}_on"
    values = np.concatenate([sub[off_column].to_numpy(float), sub[on_column].to_numpy(float)])
    log_min, log_max = np.log10(values.min()), np.log10(values.max())
    pad = max(0.08, (log_max - log_min) * 0.045)
    lower, upper = 10 ** (log_min - pad), 10 ** (log_max + pad)

    figure, axes = plt.subplots(
        1, 2, figsize=(11.0, 4.55), gridspec_kw={"width_ratios": [0.72, 1.0]}
    )
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
        [lower, upper], [lower, lower], [lower, upper], color="#EAF4EE", alpha=0.40, zorder=0,
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
    legend_labels = families.copy()
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
        bbox_to_anchor=(0.5, 0.975), frameon=False, borderaxespad=0.0,
        handlelength=1.7, handletextpad=0.30, columnspacing=0.82,
    )
    speedup_distribution(distribution_axis, sub, families)

    for label, axis in zip(
        ("(a) Running Time Comparison", "(b) Speed-up Comparison"), axes
    ):
        axis.text(0.5, -0.125, label, transform=axis.transAxes, ha="center", va="top",
                  fontsize=11, fontweight="semibold")
    figure.subplots_adjust(left=0.075, right=0.99, bottom=0.16, top=0.895, wspace=0.08)
    save_page(pdf, figure)


def complete_phase_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    seconds_columns = [seconds for _, seconds, _, _ in PHASES]
    ratio_columns = [ratio for _, _, ratio, _ in PHASES]
    wall_column = "profile_wall_time_s" if "profile_wall_time_s" in frame else "profile_total_time_s"
    required = seconds_columns + ratio_columns + [wall_column]
    if not set(required).issubset(frame.columns):
        return frame.iloc[0:0].copy(), 0
    plans = frame.get("selected_plan", pd.Series("", index=frame.index)).astype(str).str.upper()
    correct = frame.get("correct", pd.Series("TRUE", index=frame.index)).astype(str).str.upper().eq("TRUE")
    selected = frame.loc[plans.eq("OUTERYAN") & correct].copy()
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
    keys = set(zip(profiles.get("family", []), profiles.get("query", [])))
    sample = representative_runtime_rows(
        frame, limit, scope, eligible_queries=keys if has_profiles and scope == "outeryan" else None
    )
    if profiles.empty or sample.empty:
        return sample, profiles.iloc[0:0].copy()
    identity = ["family", "query", "short_query", "topology", "_family_available"]
    paired = sample[identity].merge(
        profiles.drop(columns=[c for c in identity if c not in ("family", "query")], errors="ignore"),
        on=["family", "query"], how="inner", sort=False, validate="one_to_one",
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


def page_phase(
    pdf: PdfPages, frame: pd.DataFrame, run: str, notice: str | None = None, preselected: bool = False,
) -> None:
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
    height = max(6.2, 1.45 + 0.225 * len(sub) + 0.10 * max(len(families) - 1, 0))
    if has_runtime_comparison:
        figure, (axis, runtime_axis) = plt.subplots(
            1, 2, sharey=True, figsize=(15.6, height),
            gridspec_kw={"width_ratios": [5.15, 1.30], "wspace": 0.075},
        )
    else:
        figure, axis = plt.subplots(figsize=(13.8, height))
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
            y, widths, left=left, height=0.72, color=color, edgecolor="white",
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
        axis.text(101.2, row_y, f"{total:.1f} s", ha="left", va="center", fontsize=8)

    for family in families:
        axis.text(
            -0.074, family_centers[family], "Graph" if family == "graph" else family,
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
            color=C_T1, edgecolor="white", linewidth=0.25, zorder=3,
        )
        runtime_axis.scatter(
            outeryan_runtime[runtime_valid], y[runtime_valid], marker="D", s=42,
            color=C_TM, edgecolor="white", linewidth=0.25, zorder=4,
        )
        runtime_values = np.concatenate([
            baseline_runtime[runtime_valid], outeryan_runtime[runtime_valid]
        ])
        log_min, log_max = np.log10(runtime_values.min()), np.log10(runtime_values.max())
        pad = max(0.08, (log_max - log_min) * 0.06)
        runtime_axis.set_xscale("log")
        runtime_axis.set_xlim(10 ** (log_min - pad), 10 ** (log_max + pad))
        runtime_axis.set_xlabel("Running time: DuckDB vs. OuterYan")
        runtime_axis.tick_params(axis="x", which="both", direction="in", top=True)
        runtime_axis.tick_params(axis="y", left=False, right=True, labelleft=False)
        runtime_axis.grid(axis="x", which="major", color="0.90", linewidth=0.55)
        runtime_axis.grid(axis="x", which="minor", color="0.96", linewidth=0.35)
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
        handles=phase_handles, ncol=4, fontsize=10.2, loc="lower center", frameon=False,
        bbox_to_anchor=(0.50, 1.005), borderaxespad=0.15,
    )
    if runtime_axis is not None:
        runtime_axis.legend(
            handles=[
                Line2D([], [], color=C_T1, marker="o", linestyle="none", markersize=5.8,
                       label="DuckDB baseline"),
                Line2D([], [], color=C_TM, marker="D", linestyle="none", markersize=6.0,
                       label="OuterYan enabled"),
            ],
            ncol=2, fontsize=9.2, loc="lower center", frameon=False,
            bbox_to_anchor=(0.50, 1.005), borderaxespad=0.15,
            columnspacing=0.8, handletextpad=0.35,
        )
    figure.text(
        0.52, 0.045,
        "(1) Each bar sums to profiled CPU time; segment labels are accumulated operator seconds.",
        ha="center", va="bottom", fontsize=8.7,
    )
    figure.text(
        0.52, 0.018, "(2) " + QUERY_CODE_KEY,
        ha="center", va="bottom", fontsize=8.7,
    )
    figure.subplots_adjust(left=0.116, right=0.932, bottom=0.120, top=0.865 if notice else 0.910)
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
    output_directory: Path, frame: pd.DataFrame, run: str, metric: str,
    sample_per_family: int = REPRESENTATIVE_QUERIES_PER_FAMILY,
    representative_scope: str = "outeryan",
    phase_placeholder: pd.DataFrame | None = None,
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
        (output_directory / filename).unlink(missing_ok=True)
    outputs = [("speedup_all_queries", lambda pdf: page_speedup_scatter(pdf, frame, run, metric))]
    phase_frame, notice = phase_source(frame, phase_placeholder)
    _, phases = paired_representative_samples(frame, phase_frame, sample_per_family, representative_scope)
    if not phases.empty:
        outputs.append(("phase_breakdown_outeryan", lambda pdf: page_phase(pdf, phases, run, notice, True)))
        columns = [column for column in (
            "run", "query", "short_query", "family", "topology", "selected_plan", "profile_threads",
            "profile_round1_operator_s", "profile_round2_operator_s", "profile_round3_operator_s",
            "profile_other_elapsed_s", "profile_wall_time_s", "profile_total_time_s",
            "profile_cpu_time_s",
            "_phase_sum_s", "_phase_sum_error_s", "baseline_time_s", "tm_on", "baseline_threads",
            "_family_available",
        ) if column in phases]
        (output_directory / "phase_queries.json").write_text(json.dumps({
            "placeholder": notice is not None,
            "notice": notice,
            "queries": json.loads(phases[columns].to_json(orient="records", double_precision=15)),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths: list[Path] = []
    for stem, draw in outputs:
        paths.append(write_figure_pair(output_directory, stem, draw))
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
        help="also write speedup_all_queries.pdf and phase_breakdown_outeryan.pdf "
             "(the phase figure is emitted only when profiles exist); "
             "multiple runs receive timestamp subdirectories",
    )
    parser.add_argument(
        "--phase-placeholder-csv", nargs="+",
        help="explicit legacy CSV/attempts for a visibly labeled phase placeholder only when current profiles "
             "are absent; never included in current timings or statistics (one current run only)",
    )
    parser.add_argument(
        "--representatives-per-benchmark", type=int, default=REPRESENTATIVE_QUERIES_PER_FAMILY,
        help="target representatives per benchmark (default 15); smaller eligible families are shown in full",
    )
    parser.add_argument(
        "--representative-scope", choices=["all", "outeryan"], default="outeryan",
        help="sample only OuterYan-selected queries (default), or all correct, completely timed queries",
    )
    parser.add_argument(
        "--statistics-dir",
        help="write STATISTICS.md and statistics.json (default: split output directory, or OUTPUT_STEM_statistics)",
    )
    parser.add_argument(
        "--metric", choices=["t1", "tm"], default="tm",
        help="thread setting for all-query dots; selected bars use TM only for new runs, both for legacy runs",
    )
    args = parser.parse_args()
    if args.representatives_per_benchmark < 1:
        parser.error("--representatives-per-benchmark must be positive")

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
    placeholder = None
    if args.phase_placeholder_csv:
        if frame["run"].nunique() != 1:
            parser.error("--phase-placeholder-csv requires exactly one current run")
        placeholder = load(resolve_inputs(args.phase_placeholder_csv, Path.cwd()))
        try:
            phase_source(frame, placeholder)
        except ValueError as exc:
            parser.error(str(exc))
    measured = timed(frame)
    print(f"\n{len(measured)} timed rows across {measured['run'].nunique()} logical run(s)")
    with PdfPages(output) as pdf:
        metadata = pdf.infodict()
        metadata["Title"] = "OuterYan unified benchmark figures"
        metadata["Subject"] = "ON/OFF speed-up and phase breakdown"
        metadata["Author"] = "DuckYanOuter auto_test"
        for run in dict.fromkeys(frame["run"]):
            population = frame.loc[frame["run"].eq(run)].copy()
            sub = measured.loc[measured["run"].eq(run)].copy()
            skipped = int(frame["run"].eq(run).sum() - len(sub))
            print(f"\n>>> unified run {run}: {len(sub)} timed, {skipped} skipped")
            page_summary(pdf, sub, run)
            page_shape_relations(pdf, sub, run)
            page_speedup_scatter(pdf, population, run, args.metric)
            phase_frame, notice = phase_source(population, placeholder)
            _, phases = paired_representative_samples(
                population, phase_frame, args.representatives_per_benchmark, args.representative_scope
            )
            page_phase(pdf, phases, run, notice, preselected=True)
        page_run_comparison(pdf, measured)
    print(f"\nwrote one PDF: {output}")

    if args.split_output_dir:
        split_root = Path(os.path.expanduser(args.split_output_dir))
        if not split_root.is_absolute():
            split_root = Path.cwd() / split_root
        runs = list(dict.fromkeys(frame["run"]))
        for run in runs:
            sub = frame.loc[frame["run"].eq(run)].copy()
            run_directory = split_root / run if len(runs) > 1 else split_root
            write_standalone_runtime_figures(
                run_directory, sub, run, args.metric, args.representatives_per_benchmark,
                args.representative_scope, placeholder
            )

    from benchmark_statistics import write_statistics

    statistics_root = Path(os.path.expanduser(
        args.statistics_dir or args.split_output_dir or str(output.with_name(output.stem + "_statistics"))
    )).resolve()
    runs = list(dict.fromkeys(frame["run"]))
    for run in runs:
        run_directory = statistics_root / run if len(runs) > 1 else statistics_root
        # Pass the full deduplicated run, not the timed/representative subset.
        write_statistics(run_directory, frame.loc[frame["run"].eq(run)], args.metric,
                         [path for path in paths if result_source(path)[0] == run])
        print(f"  wrote complete statistics: {run_directory}")


if __name__ == "__main__":
    main()
