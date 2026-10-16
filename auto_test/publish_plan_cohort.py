#!/usr/bin/env python3
"""Publish the active workload with measured/default/capped observations distinct.

No SQL benchmark executions or historical best-run selection occur here. New-run
inputs must cover the active manifest exactly and match every SQL content hash.
"""
import argparse
from collections import Counter
import math
from pathlib import Path
import subprocess
from unittest.mock import patch

import gen_experiment_result as plot
import report_plan_cohort as report

FAMILIES = ("graph", "tpch", "tpcds", "job")
PLOT_FAMILY = dict(graph="graph", tpch="TPC-H", tpcds="TPC-DS", job="JOB")
PHASE_KEYS = ("round1", "round2", "round3", "other")
PHASE_SELECTION = (
    "First two in display order from each family's four phase-diverse, faster/equal representatives; "
    "prefer Other OP <=50%. Replace the three reviewed short-running representatives with "
    "specified complete measured pairs having both runtimes >1 s and speed-up >1."
)
# Presentation-only substitutions. Never change the workload or aggregate statistics.
PHASE_REPLACEMENTS = {
    "graph__graph__graph_chain5_converging__left_deep__rilf__20d56999__inputcap1__sel_medium":
        "graph__graph__graph_branch5_forward__left_deep__lirf__c23c9bae__inputcap1__sel_medium",
    "join__tpcds__sqlstorm_tpcds_28643__left_deep__ifilr__b21fdfc2__sel_low":
        "aggregate__tpcds__recovery__q05_right_count__lrf__e314b93a__sel_medium",
    "join__job__job_01a_skeleton__left_deep__ilfr__01bf30c5__sel_high":
        "join__job__job_17a_movie_annotations__left_deep__irfl__4c344f38__sel_high",
}


def labeled_frame(details, observations):
    """Use stable IDs from the full frozen predecessor, not performance ranks."""
    manifest = report.b.validate(report.b.ROOT / "benchmark")
    metadata = {r["query_id"]: r for r in manifest}
    prior = report.cohort.archived_rows(report.cohort.policy())
    identities = plot.pd.DataFrame([dict(query=r["query_id"], family=PLOT_FAMILY[r["family"]],
        topology=r["tree_shape"].replace("_", "-"), workload_category=r["query_class"]) for r in prior])
    labels = plot.add_short_query_labels(identities).set_index("query").short_query.to_dict()
    for replacement in report.cohort.query_updates.policy()["replacements"]:
        labels[replacement["query_id"]] = labels[replacement["original_query"]]
    derived = {r["query"]: r for r in details}
    records = []
    for original in observations:
        raw = dict(original)
        query = raw["query"]
        meta = metadata[query]
        raw.update(derived[query])
        raw.update(short_query=labels[query], family=PLOT_FAMILY[meta["family"]],
                   topology=meta["tree_shape"].replace("_", "-"),
                   workload_category=meta["query_class"], relation_count=int(meta["relation_count"]),
                   sql_path=str((report.b.ROOT / "benchmark" / meta["path"]).resolve()),
                   run="active-cohort", source_run=original.get("source_run", original.get("experiment_group", "")))
        records.append(raw)
    frame = plot.pd.DataFrame(records)
    numeric = ["tm_off", "tm_on", "profile_total_time_s", "profile_cpu_time_s", "profile_wall_time_s",
               "optimizer_duckdb_total_s", "optimizer_outeryan_total_s", "profile_threads"]
    numeric += [col for _, seconds, ratio, _ in plot.PHASES for col in (seconds, ratio)]
    for column in numeric:
        frame[column] = plot.pd.to_numeric(frame.get(column, float("nan")), errors="coerce")
    return frame, manifest


def runtime_plot(pdf, frame):
    """All reporting ratios; only available effective pairs have 2D coordinates."""
    plot._load_plotting()
    np, plt = plot.np, plot.plt
    valid = frame.loc[frame.speedup.notna()].copy()
    if valid.empty:
        empty_plot(pdf, "No eligible reported speed-ups in this run")
        return
    pairs = valid.loc[valid.effective_duckdb_s.notna()]
    figure, (left, right) = plt.subplots(1, 2, figsize=(10.7, 3.25),
                                       gridspec_kw={"width_ratios": [.66, 1.42]})
    figure.subplots_adjust(left=.075, right=.99, bottom=.17, top=.90, wspace=.13)
    values = pairs[["effective_duckdb_s", "effective_outeryan_s"]].to_numpy(float).ravel()
    if len(values):
        low, high = np.log10(values.min()), np.log10(values.max())
        padding = max(.08, .04 * (high - low))
        plot.style_log_runtime_axis(left, 10 ** (low - padding), 10 ** (high + padding))
    # Shorten both panels together without shrinking the scatter width or
    # reopening the central gap. Equal-time coordinates remain unchanged.
    left.set_aspect("auto")
    for family in plot.FAMILY_ORDER:
        rows = valid.loc[valid.family.eq(family)].sort_values("query")
        for treatment, marker in (("measured", "o"), ("duckdb_timeout_600s", "^")):
            subset = rows.loc[rows.speedup_source.eq(treatment)]
            for faster, sign in ((True, marker), (False, "X" if treatment == "measured" else marker)):
                shown = subset.loc[subset.speedup.ge(1).eq(faster)]
                left.scatter(shown.effective_duckdb_s, shown.effective_outeryan_s,
                             color=plot.FAMILY_COLORS[family], marker=sign, s=28,
                             alpha=.55, linewidth=.35, edgecolor="white", zorder=3)
    left.set_xlabel("DuckDB running time (s)")
    left.set_ylabel("OuterYan running time (s)")
    # Density is estimated in log-ratio space; triangles distinguish timeout proxies.
    all_logs = np.log10(valid.speedup.to_numpy(float))
    lower, upper = min(-.12, all_logs.min() - .08), max(.12, all_logs.max() + .12)
    for position, family in enumerate(plot.FAMILY_ORDER):
        rows = valid.loc[valid.family.eq(family)].sort_values(["speedup", "query"])
        if rows.empty:
            continue
        logs = np.log10(rows.speedup.to_numpy(float))
        color = plot.FAMILY_COLORS[family]
        if len(logs) > 1 and np.ptp(logs) > 1e-10:
            violin = right.violinplot([logs], positions=[position], orientation="horizontal", widths=.68,
                                     showmeans=False, showmedians=False, showextrema=False)
            for body in violin["bodies"]:
                body.set_facecolor(color)
                body.set_edgecolor(color)
                body.set_alpha(.14)
        y = position + ((np.arange(len(rows)) * .61803398875) % 1 - .5) * .38
        for treatment, marker in (("measured", "o"), ("duckdb_timeout_600s", "^"),
                                  ("fallback_default_1x", "o")):
            mask = rows.speedup_source.eq(treatment).to_numpy()
            right.scatter(logs[mask], y[mask], marker=marker, s=28, alpha=.55, zorder=3,
                          facecolors=color, edgecolors="white", linewidths=.35)
        q1, med, q3 = np.quantile(logs, [.25, .5, .75])
        right.plot([q1, q3], [position, position], color=color, linewidth=3, zorder=4)
        right.scatter(med, position, marker="D", s=25, facecolor="white", edgecolor=color, zorder=5)
    right.axvline(0, color=".45", linewidth=.8)
    right.set_xlim(lower, upper)
    ticks = np.array([.8, 1, 2, 3, 4, 5, 10, 100, 1000, 10000], dtype=float)
    ticks = ticks[(np.log10(ticks) >= lower) & (np.log10(ticks) <= upper)]
    right.set_xticks(np.log10(ticks), [f"{v:g}" for v in ticks])
    for value, label in zip(ticks, right.get_xticklabels()):
        if value == .8:
            # Leave room for the nearby 1 tick without moving either tick.
            label.set_horizontalalignment("right")
    right.set_yticks(range(4), ["SGPB", "TPC-H", "TPC-DS", "JOB"])
    right.set_ylim(3.6, -.6)
    right.set_xlabel("DuckDB vs. OuterYan (log scale)")
    right.set_axisbelow(True)
    right.grid(axis="x", color=".91", linewidth=.5)
    right.tick_params(direction="in", top=True, right=True)
    right.tick_params(axis="y", pad=2)
    # Tighten the horizontal gap without changing the coordinate limits.
    right_box = right.get_position()
    right.set_position([right_box.x0 - .0035, right_box.y0, right_box.width, right_box.height])
    handles = [plot.Patch(facecolor=plot.FAMILY_COLORS[f], label=plot.figure_family_label(f))
               for f in plot.FAMILY_ORDER]
    markers = [("o", "Measured, faster/equal"), ("X", "Measured, slower"),
               ("^", "DuckDB timeout = 600 s")]
    handles += [plot.Line2D([], [], marker=m, linestyle="none", color=".3",
                           markerfacecolor=".3", label=label, markersize=5)
                for m, label in markers]
    figure.legend(handles=handles, loc="upper center", ncol=len(handles), frameon=False,
                  bbox_to_anchor=(.53, .98), fontsize=8.2, borderaxespad=.1,
                  handlelength=1.3, handletextpad=.45, columnspacing=1.10)
    # Keep both captions aligned, with a small point-sized gap below x labels.
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    label_bottom = min(axis.xaxis.label.get_window_extent(renderer).y0 for axis in (left, right))
    title_y = (label_bottom - 2.5 * figure.dpi / 72) / figure.bbox.height
    for axis, title in ((left, "(a) Running Time Comparison"), (right, "(b) Speed-up Comparison")):
        box = axis.get_position()
        figure.text(box.x0 + box.width / 2, title_y, title, ha="center", va="top",
                    fontsize=9.2, fontweight="semibold")
    with plt.rc_context({"savefig.pad_inches": .04}):
        plot.save_page(pdf, figure)


def empty_plot(pdf, message):
    plot._load_plotting()
    figure, axis = plot.plt.subplots(figsize=(8, 3))
    axis.text(.5, .5, message, transform=axis.transAxes, ha="center", va="center")
    axis.set_axis_off()
    plot.save_page(pdf, figure)


def phase_summary(frame):
    # This is an ON-only metric: a baseline timeout does not invalidate a
    # completed OuterYan profile. Keep runtime-pair and phase cohorts separate.
    selected = frame.loc[frame.selected_plan.eq("OUTERYAN")]
    complete, rejected = plot.complete_phase_rows(selected, include_duckdb_timeouts=True)
    if "profile_status" in complete:
        complete = complete.loc[complete.profile_status.eq("OK")]
    rows = []
    for family in (*plot.FAMILY_ORDER, "All"):
        sub = complete if family == "All" else complete.loc[complete.family.eq(family)]
        total = float(sub._profile_cpu_time.sum()) if len(sub) else 0
        row = dict(family=plot.figure_family_label(family), n=len(sub), operator_total_s=total)
        for key, (_, seconds, _, _) in zip(PHASE_KEYS, plot.PHASES):
            row[key + "_s"] = float(sub[seconds].sum()) if len(sub) else 0
            row[key + "_pct"] = 100 * row[key + "_s"] / total if total else None
        rows.append(row)
    return complete, rows, rejected


def workload_summary(manifest):
    summary, dimensions = [], []
    for family in (*FAMILIES, "All"):
        rows = [r for r in manifest if family == "All" or r["family"] == family]
        rel = [int(r["relation_count"]) for r in rows]
        outer = [sum(c in "LRF" for c in r["join_vector"]) for r in rows]
        counts = Counter(r["tree_shape"] for r in rows)
        aggregates = sum(r["query_class"] == "aggregate" for r in rows)
        summary.append(dict(family=report.LABELS.get(family, family), n=len(rows),
            full_result_queries=len(rows) - aggregates, aggregation_queries=aggregates,
            left_deep=counts["left_deep"], right_deep=counts["right_deep"], bushy=counts["bushy"],
            relations_min=min(rel), relations_median=report.statistics.median(rel),
            relations_max=max(rel), relations_mean=report.statistics.mean(rel),
            outer_joins_min=min(outer), outer_joins_max=max(outer)))
        for dimension in ("source_benchmark", "relation_count", "tree_shape", "topology", "semantic_tier"):
            for value, n in sorted(Counter(r[dimension] for r in rows).items()):
                dimensions.append(dict(family=report.LABELS.get(family, family), dimension=dimension, value=value, n=n))
    return summary, dimensions


def optimizer_representatives(frame):
    sub = frame.loc[frame.speedup_source.eq("measured") & frame.selected_plan.eq("OUTERYAN")
                    & frame.speedup.ge(1) & frame.tm_off.gt(1) & frame.tm_on.gt(1)
                    & frame.optimizer_profile_status.eq("OK")].copy()
    for col in ("optimizer_duckdb_total_s", "optimizer_outeryan_total_s"):
        sub = sub.loc[plot.np.isfinite(sub[col]) & sub[col].gt(0)]
    chosen = []
    for family in plot.FAMILY_ORDER:
        candidates = sub.loc[sub.family.eq(family)].sort_values(["tm_off", "query"])
        used_shapes = Counter()
        family_picks = 0
        while len(candidates) and family_picks < 3:
            # Shape coverage first; then nearest to the median baseline runtime.
            center = float(candidates.tm_off.median())
            best = min(candidates.index, key=lambda i: (used_shapes[candidates.loc[i, "topology"]],
                abs(math.log(float(candidates.loc[i, "tm_off"]) / center)), candidates.loc[i, "query"]))
            row = candidates.loc[best]
            chosen.append(row)
            family_picks += 1
            used_shapes[row.topology] += 1
            candidates = candidates.drop(best)
    records, catalogs = [], {}
    for row in chosen:
        record = dict(query=row.query, short_query=row.short_query, family=plot.figure_family_label(row.family),
            relation_count=int(row.relation_count), duckdb_s=float(row.tm_off), outeryan_s=float(row.tm_on),
            duckdb_optimizer_ms=1000 * row.optimizer_duckdb_total_s,
            outeryan_optimizer_ms=1000 * row.optimizer_outeryan_total_s,
            duckdb_optimizer_percent=100 * row.optimizer_duckdb_total_s / row.tm_off,
            outeryan_optimizer_percent=100 * row.optimizer_outeryan_total_s / row.tm_on,
            source_csv=row.source_csv, sql_content_sha256=row.sql_content_sha256)
        try:
            # Catalog inspection only; no timed benchmark SQL is executed.
            exact = row.copy()
            exact["original_sql_path"] = row.sql_path
            record.update(plot.query_attributes(exact, catalogs))
            record["attribute_status"] = "OK"
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            record.update(attribute_count=None, attribute_status=str(error))
        records.append(record)
    return records


def write_shape_results(out, details, manifest):
    by_id = {r["query_id"]: r for r in manifest}
    rows = []
    for shape in ("left_deep", "right_deep", "bushy"):
        subset = [r for r in details if by_id[r["query"]]["tree_shape"] == shape]
        for family in (*FAMILIES, "All"):
            row = report.summarize(subset, family, "all_queries")
            row["shape"] = shape
            rows.append(row)
    report.b.write_csv(out / "shape_statistics.csv", rows)


def split_optimizer_representatives(reps):
    main = []
    for family in ("SGPB", "TPC-H", "TPC-DS"):
        candidates = [r for r in reps if r["family"] == family]
        if candidates:
            main.append(candidates[0])
    main_ids = {r["query"] for r in main}
    return main, [r for r in reps if r["query"] not in main_ids]


def write_latex_tables(out, stats, phases, workload, reps):
    """One generated table bundle; never write manuscript prose or fragments."""
    def text(value):
        escapes = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%",
                   "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
                   "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
        return "".join(escapes.get(c, c) for c in str(value))

    def number(value, digits=2):
        if value is None or not math.isfinite(float(value)):
            return "--"
        return r"\fix{" + f"{float(value):.{digits}f}" + "}"

    sections = ["% Generated tables only. Requires booktabs and graphicx.\n"
                r"\providecommand{\fix}[1]{#1}" + "\n"]

    def table(caption, headers, rows):
        lines = [r"\begin{table*}[t]", r"\centering\scriptsize",
                 r"\caption{" + caption + "}", r"\resizebox{\textwidth}{!}{%",
                 r"\begin{tabular}{" + "l" * len(headers) + "}", r"\toprule",
                 " & ".join(headers) + r" \\", r"\midrule"]
        lines.extend(" & ".join(row) + r" \\" for row in rows)
        lines += [r"\bottomrule", r"\end{tabular}}", r"\end{table*}"]
        sections.append("\n".join(lines) + "\n")

    for scope, label in (("all_queries", "All eligible queries"),
                         ("outeryan_selected", "OuterYan-selected queries")):
        rows = [[text(r["family"]), number(r["n"], 0)] +
                [number(r[k], 4) for k in ("geomean", "min", "median", "max")]
                for r in stats if r["scope"] == scope]
        table("Speed-up of OuterYan over DuckDB: " + label +
              ". DuckDB-only timeouts use a 600 s proxy; skipped fallbacks use "
              r"$1\times$ where included. Neither is a measured pair.",
              ["Group", "$n$", "Geomean", "Min", "Median", "Max"], rows)
    phase_rows = []
    for row in phases:
        values = [row[k + "_pct"] for k in PHASE_KEYS]
        # Largest-remainder rounding makes the displayed percentages sum to 100.
        if all(v is not None for v in values):
            floors = [math.floor(v * 100) for v in values]
            missing = 10000 - sum(floors)
            for i in sorted(range(4), key=lambda i: (-(values[i] * 100 - floors[i]), i))[:missing]:
                floors[i] += 1
            values = [v / 100 for v in floors]
        phase_rows.append([text(row["family"]), number(row["n"], 0)] +
                          [number(v) + (r"\%" if v is not None else "") for v in values])
    table("Execution round breakdown of OuterYan (summed operator times).",
          ["Group", "$n$", "Round 1", "Round 2", "Round 3", "Other OP"], phase_rows)
    table("Benchmark composition.",
          ["Group", "$n$", "Full result", "Aggregation", "Left-deep", "Right-deep", "Bushy"],
          [[text(r["family"])] + [number(r[k], 0) for k in
            ("n", "full_result_queries", "aggregation_queries", "left_deep", "right_deep", "bushy")]
           for r in workload])
    metrics = [("Running time (s)", "duckdb_s", "outeryan_s", 3),
               ("Optimization time (ms)", "duckdb_optimizer_ms", "outeryan_optimizer_ms", 3),
               (r"Optimization ratio (\%)", "duckdb_optimizer_percent", "outeryan_optimizer_percent", 4)]
    for name, chosen in zip(("Main", "Additional"), split_optimizer_representatives(reps)):
        if not chosen:
            continue
        rows = [["Query statistics", r"\# Tables"] + [number(r["relation_count"], 0) for r in chosen],
                ["", r"\# Attributes"] + [number(r.get("attribute_count"), 0) for r in chosen]]
        for label, off, on, digits in metrics:
            rows += [[label, "DuckDB"] + [number(r[off], digits) for r in chosen],
                     ["", "OuterYan"] + [number(r[on], digits) for r in chosen]]
        table(name + " optimization-time representatives.",
              ["Category", "Metric"] + [text(r["short_query"]) for r in chosen], rows)
    (out / "tables.tex").write_text("\n".join(sections), encoding="utf-8")


def replace_short_phase_representatives(frame, samples):
    """Keep other sample rows intact and apply reviewed replacements when eligible."""
    if samples.empty or not samples["query"].isin(PHASE_REPLACEMENTS).any():
        return samples.copy()
    eligible, _ = plot.complete_phase_rows(frame)
    eligible = eligible.loc[
        eligible.speedup_source.eq("measured") & eligible.profile_status.eq("OK")
        & eligible.tm_off.gt(1) & eligible.tm_on.gt(1) & eligible.tm_off.gt(eligible.tm_on)
    ]
    result = []
    used = set(samples["query"])
    for _, original in samples.iterrows():
        target = PHASE_REPLACEMENTS.get(original["query"])
        replacement = eligible.loc[eligible["query"].eq(target)]
        if len(replacement) == 1 and target not in used and replacement.iloc[0].family == original.family:
            row = replacement.iloc[0].copy()
            row["baseline_time_s"] = row.tm_off
            row["baseline_threads"] = row.get("timing_threads", row.get("profile_threads"))
            row["_phase_other_limit"] = .5
            row["_phase_other_limit_relaxed"] = row.profile_other_ratio > .5
            used.remove(original["query"])
            used.add(target)
            result.append(row)
        else:
            # A new run may lack a complete, faster replacement; never fabricate one.
            result.append(original.copy())
    return plot.pd.DataFrame(result).reset_index(drop=True)


def phase_figure_samples(frame):
    """Keep the first two displayed rows of the existing four-query sample."""
    samples = plot.diverse_phase_samples(frame, 4, .5)
    if samples.empty:
        return samples
    ranks = {
        "family": {name: i for i, name in enumerate(plot.FAMILY_ORDER)},
        "topology": {name: i for i, name in enumerate(plot.TOPOLOGY_ORDER + ["other"])},
    }
    ordered = samples.sort_values(
        ["family", "topology", "short_query"], kind="stable",
        key=lambda column: column.map(ranks[column.name]).fillna(99) if column.name in ranks else column,
    )
    samples = ordered.groupby("family", sort=False).head(2).copy()
    return replace_short_phase_representatives(frame, samples)


def publish(out, csv_paths=None, figures=True):
    plot.MIN_RUNTIME_SECONDS = 0
    details, retired, stats, summary = report.build(csv_paths)
    out.mkdir(parents=True, exist_ok=True)
    report.b.write_csv(out / "plan_cohort_statistics.csv", stats)
    _, _, observations, _ = report.load_observations(csv_paths)
    frame, manifest = labeled_frame(details, observations)
    measured = frame.loc[frame.speedup_source.eq("measured")]
    summary["measurement_protocol"] = {
        key: dict(Counter(measured[key].fillna("").astype(str))) if key in measured else {}
        for key in ("timing_samples", "timing_estimator", "warmup_runs_per_side", "correctness_check", "timing_threads")}
    complete, phases, rejected = phase_summary(frame)
    report.b.write_csv(out / "phase_summary.csv", phases)
    workload, dimensions = workload_summary(manifest)
    report.b.write_csv(out / "benchmark_composition.csv", workload)
    report.b.write_csv(out / "benchmark_dimensions.csv", dimensions)
    write_shape_results(out, details, manifest)
    reps = optimizer_representatives(frame)
    main, appendix = split_optimizer_representatives(reps)
    main_queries = {r["query"] for r in main}
    for row in reps:
        row["table_group"] = "main" if row["query"] in main_queries else "appendix"
    if reps:
        report.b.write_csv(out / "optimization_representatives.csv", reps)
    else:
        (out / "optimization_representatives.csv").write_text("query,short_query,attribute_count,table_group\n")
    selection = dict(main=[r["short_query"] for r in main], appendix=[r["short_query"] for r in appendix])
    samples = phase_figure_samples(frame)
    # Keep one per-query table: subsets and plot IDs can be recovered by filtering
    # these columns, without copying the full observations into several files.
    frame["phase_summary_included"] = frame["query"].isin(complete["query"])
    frame["phase_figure_order"] = frame["query"].map(
        {query: index for index, query in enumerate(samples["query"], 1)})
    frame["optimization_table_group"] = frame["query"].map(
        {row["query"]: row["table_group"] for row in reps}).fillna("")
    frame.to_csv(out / "current_results.csv", index=False)
    if figures:
        plot.write_figure_pair(out, "speedup_all_queries", lambda pdf: runtime_plot(pdf, frame))
        save = plot.save_page

        def operator_labels(pdf, figure):
            for axis in figure.axes:
                if axis.get_xlabel() == "CPU Time (%)":
                    axis.set_xlabel("Operator time (%)")
            save(pdf, figure)

        if len(samples):
            with patch.object(plot, "save_page", operator_labels), \
                 patch.object(plot, "PROFILE_CPU_TOTAL_LABEL", "Total operator time"):
                plot.write_figure_pair(out, "phase_breakdown_outeryan",
                                      lambda pdf: plot.page_phase(pdf, samples, "active-cohort", preselected=True))
        else:
            plot.write_figure_pair(out, "phase_breakdown_outeryan",
                                  lambda pdf: empty_plot(pdf, "No eligible representative phase profiles in this run"))
    # Preserve exclusions and provenance in the single metadata file, not an
    # empty or duplicate results CSV. Existing historical files are not removed.
    summary.update(phase_profiles=len(complete), phase_rejected=rejected, figures_refreshed=figures,
                   retired_both_timeouts=retired,
                   phase_profile_policy="Complete OuterYan-selected operator profiles, including DuckDB-only timeouts; no substituted phase times",
                   phase_duckdb_timeout_profiles=int(complete.duckdb_status.eq("timeout").sum()),
                   optimization_representatives=selection, workload=workload,
                   phase_sample_queries=samples["query"].tolist(),
                   phase_selection=PHASE_SELECTION,
                   figure_points=dict(runtime_pairs=int(frame.effective_duckdb_s.notna().sum()),
                                      ratio_points=int(frame.speedup.notna().sum())),
                   attribute_warnings=[r["query"] for r in reps if r["attribute_status"] != "OK"])
    report.b.write_json(out / "report_metadata.json", summary)
    write_latex_tables(out, stats, phases, workload, reps)
    print(f"Published {len(frame)} query records, {len(complete)} phase profiles, {len(reps)} optimizer representatives: {out}")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=report.DEFAULT_OUT)
    parser.add_argument("--csv", type=Path, action="append", help="Complete new-run inputs only")
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args(argv)
    publish(args.output_dir.resolve(), args.csv, not args.no_figures)


if __name__ == "__main__":
    main()
