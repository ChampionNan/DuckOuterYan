#!/usr/bin/env python3
"""Refresh the fixed October 13 snapshot and only numbers in the supplied prose.

This is a reporting command: it never executes benchmark SQL. Historical input
hashes and the workload setting are checked by freeze_tpch_tuning_results.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shlex
from unittest.mock import patch

import freeze_tpch_tuning_results as frozen
import gen_experiment_result as plot
import refresh_paper_results as refresh
import tpch_tuning_promotion as promotion

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TEMPLATE = HERE / "paper_results_fixed_template.tex"
FIX = re.compile(r"\\fix\{([^{}]*)\}")
FAMILIES = ("Graph", "TPC-H", "TPC-DS", "JOB", "All")
GRAPH_CASE = "aggregate__graph__graph_branch5_converging__left_deep__filr__6a97852b__inputcap1__sel_high__global_count"


def replace_values(text, values):
    """Require a one-to-one numeric-slot match and preserve all surrounding text."""
    matches = list(FIX.finditer(text))
    if len(matches) != len(values):
        raise ValueError(f"Expected {len(matches)} fix values, received {len(values)}")
    replacements = iter(values)
    return FIX.sub(lambda _: r"\fix{" + str(next(replacements)) + "}", text)


def numeric_update(template, paper):
    groups = {r["family"]: r for r in paper["runtime"]["outeryan_selected"]}
    phase = {"All" if r["family"] == "all" else r["family"]: r for r in paper["phase"]}
    reps = {r["short_query"]: r for r in paper["representatives"]}
    times = [reps[q] for q in ("A-G-LD-05", "Q-H-LD-04", "A-D-LD-05")]
    maximum = max(reps.values(), key=lambda r: r["outeryan_optimizer_percent"])
    if maximum["short_query"] != "A-G-LD-05":
        raise ValueError("The unchanged optimization prose no longer identifies the maximum")
    pct = lambda v, digits=2: f"{v:.{digits}f}" + r"\%"
    factor = lambda v: f"${v:.2f}" + r"\times$"
    all_group = groups["All"]
    overall_values = [all_group["counts"]["valid"], factor(all_group["speedup"]["geomean"])]
    overall_values += [factor(groups[f]["speedup"]["geomean"]) for f in FAMILIES[:-1]]
    overall_values += [factor(all_group["speedup"]["max"])]
    for family in FAMILIES:
        row = groups[family]
        overall_values += [row["counts"]["valid"]]
        overall_values += [f"{row['speedup'][key]:.2f}" for key in ("geomean", "median", "max")]
    overall, remainder = template.split(r"\paragraph{Running Time Comparison.", 1)
    overall = replace_values(overall, overall_values)
    unchanged, tail = remainder.split(r"\paragraph{Execution Breakdown}", 1)
    breakdown, optimization = tail.split(r"\paragraph{Optimization Time. }", 1)
    shares = {f: r["cpu_weighted_fraction"] for f, r in phase.items()}
    phase_values = [phase["All"]["profiles"], pct(100 * shares["Graph"]["other"]),
                    pct(100 * shares["TPC-H"]["round3"]), pct(100 * shares["JOB"]["round3"]),
                    pct(100 * (shares["TPC-DS"]["round1"] + shares["TPC-DS"]["round2"])),
                    pct(100 * (shares["All"]["round1"] + shares["All"]["round2"]), 1),
                    pct(100 * shares["All"]["round3"]), pct(100 * shares["All"]["other"])]
    for family in FAMILIES:
        phase_values += [phase[family]["profiles"]]
        phase_values += [pct(100 * shares[family][key]) for key in refresh.PHASE_KEYS]
    breakdown = replace_values(breakdown, phase_values)
    below = sum(r["outeryan_optimizer_percent"] < 1 for r in reps.values())
    opt_values = [r"1\%", f"{below} of the {len(reps)} queries",
                  pct(maximum["outeryan_optimizer_percent"]), f"{times[0]['outeryan_optimizer_ms']:.3f}",
                  pct(times[0]["outeryan_optimizer_percent"]), pct(times[2]["outeryan_optimizer_percent"], 3)]
    for field, digits in (("duckdb_s", 3), ("outeryan_s", 3), ("duckdb_optimizer_ms", 3),
                          ("outeryan_optimizer_ms", 3), ("duckdb_optimizer_percent", 4),
                          ("outeryan_optimizer_percent", 4)):
        opt_values += [f"{r[field]:.{digits}f}" for r in times]
    optimization = replace_values(optimization, opt_values)
    result = (overall + r"\paragraph{Running Time Comparison." + unchanged
              + r"\paragraph{Execution Breakdown}" + breakdown
              + r"\paragraph{Optimization Time. }" + optimization)
    if FIX.sub(r"FIX", result) != FIX.sub(r"FIX", template):
        raise ValueError("Text outside fix changed")
    return result


def label_map():
    # Retain the already published slots rather than renumbering changed SQLs.
    path = HERE / "results/plots/20261012/query_id_map.csv"
    labels = plot.pd.read_csv(path).set_index("query").short_query.to_dict()
    for row in promotion.replacements():
        labels[row["query_id"]] = labels[row["tuning_replaces_query_id"]]
    # The supplied manuscript uses this earlier alias for the same exact query.
    labels[GRAPH_CASE] = "A-G-LD-05"
    return labels


def fixed_representatives(frame, detail, limit):
    """Keep the manuscript's twelve SQL identities; refresh every measurement."""
    original = plot.pd.read_csv(HERE / "results/plots/20261007/optimization_representatives.csv")
    replacement = {r["tuning_replaces_query_id"]: r["query_id"] for r in promotion.replacements()}
    labels = label_map()
    indexed = frame.set_index("query", drop=False)
    result, catalogs = [], {}
    for old in original.itertuples():
        query = replacement.get(old.query, old.query)
        row = indexed.loc[query]
        if row.optimizer_profile_status != "OK":
            raise ValueError("Missing paired optimizer profile: " + query)
        off, on = float(row.tm_off), float(row.tm_on)
        off_opt, on_opt = float(row.optimizer_duckdb_total_s), float(row.optimizer_outeryan_total_s)
        if not all(math.isfinite(v) and v > 0 for v in (off, on, off_opt, on_opt)):
            raise ValueError("Incomplete optimization representative: " + query)
        record = {k: row[k] for k in ("query", "source_run", "source_csv", "sql_path",
                                       "workload_category", "optimizer_timed_samples")}
        record.update(short_query=labels[query], family=plot.normalize_family(row.family),
                      relation_count=int(row.csv_relation_count), duckdb_s=off, outeryan_s=on,
                      duckdb_optimizer_ms=1000 * off_opt, outeryan_optimizer_ms=1000 * on_opt,
                      duckdb_optimizer_percent=100 * off_opt / off,
                      outeryan_optimizer_percent=100 * on_opt / on)
        record.update(plot.query_attributes(row, catalogs))
        result.append(record)
    if len(result) != 12:
        raise ValueError("Expected the manuscript's 12 representatives")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=frozen.DEFAULT_OUT)
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args(argv)
    out = args.output_dir.resolve()
    for family, filename in (("GRAPH", "graph_db"), ("TPCH", "tpch_1.duckdb"),
                             ("TPCDS", "tpcds_1.duckdb"), ("JOB", "job_db")):
        os.environ.setdefault(family + "_DB", str(ROOT / filename))
    frozen.main(["--output-dir", str(out)])
    labels = label_map()

    def stable_labels(frame):
        result = frame.copy()
        result["short_query"] = result["query"].map(labels)
        if result.short_query.isna().any() or result.short_query.duplicated().any():
            raise ValueError("Missing or ambiguous fixed query label")
        return result

    save = plot.save_page

    def operator_labels(pdf, figure):
        for axis in figure.axes:
            if axis.get_xlabel() == "CPU Time (%)":
                axis.set_xlabel("Operator time (%)")
        save(pdf, figure)

    baseline = ROOT / promotion.measurement_snapshot()["baseline_csv"]
    command = [str(baseline), str(out / "frozen_20_input.csv"), "--output-dir", str(out)]
    if args.no_figures:
        command += ["--no-figures"]
    with patch.object(plot, "add_short_query_labels", stable_labels), \
         patch.object(plot, "representatives", fixed_representatives), \
         patch.object(plot, "save_page", operator_labels), \
         patch.object(plot, "PROFILE_CPU_TOTAL_LABEL", "Total operator time"):
        refresh.main(command)

    paper = json.loads((out / "paper_statistics.json").read_text())
    paper["method"]["representatives"] = "Keep the 12 manuscript query identities and update their paired measurements."
    refresh.write_json(out / "paper_statistics.json", paper)
    source = TEMPLATE.read_text()
    result = numeric_update(source, paper)
    for name in ("experiment_results.tex", "paper_updates.tex", "requested_paper_sections.tex"):
        (out / name).write_text(result)
    execution = result.split(r"\paragraph{Execution Breakdown}", 1)[1]
    (out / "execution_optimization_updates.tex").write_text(r"\paragraph{Execution Breakdown}" + execution)
    (out / "paper_replacements.tex").write_text(result.split(r"\paragraph{Execution Breakdown}", 1)[0])
    tables = re.findall(r"\\begin\{table\}.*?\\end\{table\}", result, re.S)
    if len(tables) != 3:
        raise ValueError("Expected three supplied tables")
    for name, table in zip(("runtime_by_benchmark.tex", "phase_summary.tex", "optimization_summary.tex"), tables):
        (out / name).write_text(table + "\n")
    (out / "optimization_appendix_table.tex").write_text(plot.optimization_tex(paper))
    (out / "shape_effect.tex").write_text(plot.shape_tex(paper))
    changes = [{"slot": i + 1, "old": old, "new": new}
               for i, (old, new) in enumerate(zip(FIX.findall(source), FIX.findall(result))) if old != new]
    refresh.write_json(out / "latex_numeric_update_audit.json", dict(
        template_sha256=refresh.digest(TEMPLATE), output_sha256=refresh.digest(out / "experiment_results.tex"),
        unchanged_outside_fix=True, replacements=changes,
        postgres_measurements="Retained: this benchmark rerun does not remeasure the separate PostgreSQL experiment."))
    # Human-readable tables omit arithmetic means; statistics.json keeps complete diagnostics.
    for name in ("benchmark_statistics.csv", "policy_benchmark_statistics.csv"):
        table = plot.pd.read_csv(out / name).drop(columns=["mean"], errors="ignore")
        table.to_csv(out / name, index=False)
    phase = plot.pd.read_csv(out / "phase_summary.csv").rename(columns={"cpu_total_s": "operator_total_s"})
    phase["family"] = phase.family.map(plot.figure_family_label)
    phase.to_csv(out / "phase_summary.csv", index=False)
    merged = plot.pd.read_csv(out / "merged_current_results.csv")
    selected = plot.pd.read_csv(out / "current_results.csv")
    coverage = []
    for family in FAMILIES:
        rows = merged if family == "All" else merged.loc[merged.family.map(plot.normalize_family).eq(family)]
        cohort = selected if family == "All" else selected.loc[selected.family.map(plot.normalize_family).eq(family)]
        coverage.append(dict(family=plot.figure_family_label(family), queries=len(rows),
                             valid_selected=len(cohort), fallback_skips=int(rows.timing_status.eq("fallback-skip").sum()),
                             timeouts=int(plot.timeout_mask(rows).sum()),
                             selected_including_timeouts=int(rows.selected_plan.eq("OUTERYAN").sum())))
    plot.pd.DataFrame(coverage).to_csv(out / "coverage.csv", index=False)
    audit = json.loads((out / "refresh_audit.json").read_text())
    audit["frozen_setting"] = str(promotion.POLICY)
    audit["frozen_measurement_audit"] = str(out / "frozen_20_audit.json")
    audit["manuscript_template"] = str(TEMPLATE)
    audit["representative_selection"] = paper["method"]["representatives"]
    refresh.write_json(out / "refresh_audit.json", audit)
    (out / "REPRODUCE.txt").write_text(shlex.join(["python3", str(Path(__file__).resolve()),
                                                    "--output-dir", str(out)]) + "\n")
    note = out / "FROZEN_TPCH_SETTING.txt"
    note.write_text(note.read_text().replace(
        "Run auto_test/refresh_fixed_tpch_paper.py to refresh the normal figure/statistics filenames and manuscript.",
        "Current unprefixed plots/statistics and experiment_results.tex use this fixed snapshot."))
    print(f"Updated {len(changes)} fix values; all text outside fix unchanged. Output: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
