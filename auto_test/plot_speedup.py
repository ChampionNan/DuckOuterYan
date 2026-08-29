#!/usr/bin/env python3
"""Render OuterYan ON/OFF results as one multi-page benchmark PDF.

CSV files that share a ``YYYYMMDD_HHMMSS`` timestamp are one logical run.
Consequently, historical ``core``, ``custom``, and ``industry_inspired`` CSVs
from the same invocation are merged before plotting. Attempts files fill rows
missing from the final CSV; final rows win duplicates.

The PDF contains summary and shape/relation-count pages, one per-query speed-up
page for each benchmark family, and one phase-breakdown page shared by every
family. There is intentionally no kernel-speedup view.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch


C_T1 = "#4C72B0"
C_TM = "#DD8452"
FAMILY_ORDER = ["graph", "TPC-H", "TPC-DS", "JOB"]
TOPOLOGY_ORDER = ["left-deep", "right-deep", "bushy", "star", "aggregate", "industry"]
CLASS_ORDER = ["derived", "industry", "custom", "legacy"]
CLASS_TAG = {
    "derived": "D",
    "industry": "I",
    "custom": "C",
    "legacy": "L",
}
PHASES = [
    ("R1 semi-join", "profile_round1_operator_s", "profile_round1_ratio", "#4C72B0"),
    ("R2 semi-join", "profile_round2_operator_s", "profile_round2_ratio", "#55A868"),
    ("R3 real join", "profile_round3_operator_s", "profile_round3_ratio", "#DD8452"),
    ("OtherCPU", "profile_other_elapsed_s", "profile_other_ratio", "#B0B0B0"),
]
OUTERYAN_TOTAL_LABEL = "OuterYan wall total (profiled)"
OUTERYAN_TOTAL_COLOR = "#EFCB68"
BASELINE_LABEL = "DuckDB wall total (matching-thread median)"
BASELINE_COLOR = "#F4A6B7"

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
    if "relation_count" in frame:
        valid = frame["relation_count"].where(
            frame["relation_count"].gt(0)
            & frame["relation_count"].eq(np.floor(frame["relation_count"]))
        )
        frame["relation_count"] = valid.fillna(fallback_relations)
    else:
        frame["relation_count"] = fallback_relations

    frame["display_query"] = [
        f"[{CLASS_TAG.get(query_class, '?')}] {query}"
        for query_class, query in zip(frame["query_class"], frame["query"])
    ]
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


def page_per_query(
    pdf: PdfPages, frame: pd.DataFrame, run: str, metric: str, family: str
) -> None:
    metric_column = f"{metric}_speedup"
    other_column = "t1_speedup" if metric == "tm" else "tm_speedup"
    sub = frame.dropna(subset=[metric_column]).copy()
    sub = sub.sort_values([metric_column, "query"], kind="stable")
    if sub.empty:
        return
    height = min(42.0, max(10.0, 0.205 * len(sub) + 2.2))
    figure, ax = plt.subplots(figsize=(12.0, height))
    y = np.arange(len(sub))
    bar_height = 0.38
    metric_bars = ax.barh(
        y + bar_height / 2, sub[metric_column], height=bar_height,
        color=C_TM, edgecolor="none"
    )
    other_bars = ax.barh(
        y - bar_height / 2, sub[other_column], height=bar_height,
        color="#CCCCCC", edgecolor="none"
    )
    ax.axvline(1.0, color="grey", linestyle="--", linewidth=1)
    ax.set_xscale("log")
    plans = sub.get("selected_plan", pd.Series("", index=sub.index)).astype(str).str.upper()
    plan_tags = np.select([plans.eq("OUTERYAN"), plans.eq("DUCKDB")], ["OY", "D"], default="?")
    labels = [
        f"{display} [{plan}]" for display, plan in zip(sub["display_query"], plan_tags)
    ]
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=5.2)
    ax.set_ylim(-1, len(sub))
    ax.set_xlabel("speed-up (×, log; >1 = OuterYan ON faster)")
    ax.set_title(f"{family} benchmark speed-up ({len(sub)} timed queries)")
    ax.legend(
        handles=[Patch(facecolor=C_TM, edgecolor="none", label=metric.upper()),
                 Patch(facecolor="#CCCCCC", edgecolor="none", label=other_column[:2].upper())],
        fontsize=8, loc="lower right"
    )
    figure.tight_layout()
    save_page(pdf, figure)


def pages_per_benchmark(
    pdf: PdfPages, frame: pd.DataFrame, run: str, metric: str
) -> None:
    """Write one speed-up page per family without splitting query provenance."""
    for family in FAMILY_ORDER:
        family_rows = frame.loc[frame["family"].eq(family)].copy()
        page_per_query(pdf, family_rows, run, metric, family)


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
    for column in required + ["profile_threads", "profile_cpu_time_s", "t1_off", "tm_off"]:
        if column in selected:
            selected[column] = pd.to_numeric(selected[column], errors="coerce")
    seconds = selected[seconds_columns]
    ratios = selected[ratio_columns]
    total_time = selected["profile_total_time_s"]
    cpu_time = selected.get("profile_cpu_time_s", total_time).where(
        lambda value: np.isfinite(value) & value.gt(0), total_time
    )
    threads = selected.get("profile_threads", pd.Series(np.nan, index=selected.index))
    t1_baseline = selected.get("t1_off", pd.Series(np.nan, index=selected.index))
    tm_baseline = selected.get("tm_off", pd.Series(np.nan, index=selected.index))
    baseline = t1_baseline.where(~threads.gt(1), tm_baseline)
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
        & np.isfinite(baseline)
        & baseline.gt(0)
        & np.isclose(seconds.sum(axis=1), cpu_time, rtol=1e-6, atol=1e-9)
        & ratios.sum(axis=1).sub(1.0).abs().le(1e-6)
        & np.isclose(
            ratios.to_numpy(float), seconds.div(cpu_time, axis=0).to_numpy(float), atol=1e-6
        ).all(axis=1)
    )
    selected["_baseline_time"] = baseline
    selected["_profile_cpu_time"] = cpu_time
    return selected.loc[complete].copy(), int((~complete).sum())


def page_phase(pdf: PdfPages, frame: pd.DataFrame, run: str) -> None:
    sub, skipped = complete_phase_rows(frame)
    if sub.empty:
        print(f"  phase breakdown omitted for {run}: no complete selected profiles")
        return
    sub = sub.sort_values(["family", "profile_total_time_s", "query"], kind="stable")
    seconds_columns = [seconds for _, seconds, _, _ in PHASES]
    positive = sub[seconds_columns].to_numpy(float)
    positive = positive[positive > 0]
    if not positive.size:
        return
    height = min(32.0, max(7.0, 0.48 * len(sub) + 2.0))
    figure, ax = plt.subplots(figsize=(13.0, height))
    y = np.arange(len(sub)) * 1.05
    bar_height = 0.12
    totals = sub["profile_total_time_s"].to_numpy(float)
    baselines = sub["_baseline_time"].to_numpy(float)
    axis_floor = 10 ** np.floor(np.log10(min(positive.min(), totals.min(), baselines.min())))
    offsets = (np.arange(len(PHASES) + 2) - (len(PHASES) + 1) / 2) * bar_height
    for offset, (label, seconds, _, color) in zip(offsets[1:-1], PHASES):
        values = sub[seconds].to_numpy(float)
        present = values > 0
        bars = ax.barh(
            y[present] + offset, values[present] - axis_floor, left=axis_floor,
            height=bar_height, color=color, edgecolor="none", label=label
        )
    total_bars = ax.barh(
        y + offsets[0], totals - axis_floor, left=axis_floor, height=bar_height,
        color=OUTERYAN_TOTAL_COLOR, edgecolor="none", label=OUTERYAN_TOTAL_LABEL
    )
    baseline_bars = ax.barh(
        y + offsets[-1], baselines - axis_floor, left=axis_floor, height=bar_height,
        color=BASELINE_COLOR, edgecolor="none", label=BASELINE_LABEL
    )
    ax.set_yticks(y)
    ax.set_yticklabels(
        [f"{family} | {display}" for family, display in zip(sub["family"], sub["display_query"])],
        fontsize=5.8
    )
    ax.set_xscale("log")
    ax.set_xlim(axis_floor, max(positive.max(), totals.max(), baselines.max()) * 1.10)
    ax.grid(axis="x", which="both", color="0.90", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.set_xlabel("seconds")
    omission = f"; {skipped} incomplete selected profiles omitted" if skipped else ""
    ax.set_title(
        f"All benchmark phase breakdowns in one figure ({len(sub)} queries{omission})"
    )
    phase_handles = [
        Patch(facecolor=color, edgecolor="none", label=label)
        for label, _, _, color in PHASES
    ]
    phase_handles.extend([
        Patch(facecolor=OUTERYAN_TOTAL_COLOR, edgecolor="none", label=OUTERYAN_TOTAL_LABEL),
        Patch(facecolor=BASELINE_COLOR, edgecolor="none", label=BASELINE_LABEL),
    ])
    ax.legend(handles=phase_handles, ncol=3, fontsize=7, loc="lower right")
    figure.tight_layout()
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="*", help="experiment_onoff CSV files")
    parser.add_argument(
        "-o", "--output", default=str(DEFAULT_OUTPUT),
        help="single output PDF (default: auto_test/results/plots/outeryan_benchmark_figures.pdf)"
    )
    parser.add_argument("--metric", choices=["t1", "tm"], default="tm")
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
            pages_per_benchmark(pdf, sub, run, args.metric)
            page_phase(pdf, sub, run)
        page_run_comparison(pdf, measured)
    print(f"\nwrote one PDF: {output}")


if __name__ == "__main__":
    main()
