#!/usr/bin/env python3
"""Refresh manuscript statistics and figures against the active SQL manifest.

Pass the old full result CSV and, later, a new TPC-DS result CSV together. The
latest observation of identical SQL wins, including failures. No queries run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shlex
from pathlib import Path

import pandas as pd

import gen_experiment_result as plot


HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "outerjoin_benchmark/benchmark/manifest.csv"
TEMPLATE = HERE / "paper_refresh_template.tex"
FAMILY_ORDER = ("Graph", "TPC-H", "TPC-DS", "JOB", "All")
PHASE_KEYS = ("round1", "round2", "round3", "other")
PAPER_COMPONENTS = {
    "source_derived": "structural", "historical_pattern_adaptation": "structural",
    "synthetic_graph": "evaluation", "industry_synthetic_control": "evaluation",
}
COMPOSITION_RULE = (
    "Structural = source-derived benchmark patterns, including historical pattern adaptations. "
    "Supplementary = synthetic Graph and industry controls, whether aggregated or not. "
    "Classified by manifest provenance_class, not query names or aggregation status."
)
SCREENING = (
    "Current active, outcome-screened manifest: historical query construction; "
    "13 observed speed-ups below 0.5 removed across families and 28 TPC-DS "
    "timeouts removed in the 2026-10-05 revision; the 2026-10-07 revision additionally "
    "retires 7 measured TPC-DS speed-ups below 0.5. Not an unbiased benchmark sample. "
    "Sub-second pairs are retained. Any additional speed-up cutoff is recorded explicitly."
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def current_observations(sources: list[str], manifest_path: Path, replace_tpcds: Path | None = None):
    manifest = pd.read_csv(manifest_path, keep_default_na=False)
    if manifest.query_id.duplicated().any():
        raise ValueError("Active manifest query IDs must be unique")
    active = manifest.set_index("query_id")
    for _, row in active.iterrows():
        if digest(manifest_path.parent / row.path) != row.content_sha256:
            raise ValueError(f"Active SQL does not match its manifest: {row.path}")
    loaded = plot.load(sources)
    superseded = loaded.iloc[:0].copy()
    if replace_tpcds is not None:
        replacement_source = str(replace_tpcds.resolve())
        replacement = loaded.loc[loaded.source_csv.eq(replacement_source)]
        if replacement.empty or not replacement.family.map(plot.normalize_family).eq("TPC-DS").all():
            raise ValueError("--replace-tpcds must name a nonempty, TPC-DS-only input CSV")
        replaced = loaded.family.map(plot.normalize_family).eq("TPC-DS") & ~loaded.source_csv.eq(replacement_source)
        superseded = loaded.loc[replaced].copy()
        superseded["refresh_exclusion"] = "superseded_tpcds_batch"
        loaded = loaded.loc[~replaced].copy()
    if "sql_content_sha256" not in loaded:
        raise ValueError("Result CSV must record sql_content_sha256; names alone are insufficient")
    # Never transfer a measurement to a modified query with the same name.
    expected = loaded["query"].map(active.content_sha256)
    match = expected.notna() & loaded.sql_content_sha256.eq(expected)
    rejected = loaded.loc[~match].copy()
    rejected["refresh_exclusion"] = [
        "retired_or_not_active" if name not in active.index else "changed_sql_hash"
        for name in rejected["query"]
    ]
    if not superseded.empty:
        rejected = pd.concat([rejected, superseded], ignore_index=True)
    matched = loaded.loc[match].sort_values(["source_run", "source_csv"], kind="stable")
    # Select latest status, not the latest successful observation.
    matched = matched.drop_duplicates("sql_identity", keep="last").reset_index(drop=True)
    if matched.empty:
        raise ValueError("No exact active-SQL measurements found")
    for family, rows in matched.groupby("family"):
        for column in ("timing_threads", "execution_host", "database_signature",
                       "timing_protocol", "timing_samples", "timing_estimator"):
            if column in rows and rows[column].nunique(dropna=False) != 1:
                raise ValueError(f"Incompatible {column} in {family}; do not pool these experiments")
    if matched.timing_threads.nunique() != 1:
        raise ValueError("All families must use the same timing thread count")
    matched["run"] = "active_manifest_refresh"
    if "provenance_class" in active:
        matched["provenance_class"] = matched["query"].map(active.provenance_class)
        matched["workload_component"] = matched.provenance_class.map(PAPER_COMPONENTS)
        if matched.workload_component.isna().any():
            raise ValueError("Unknown provenance_class; cannot infer structural/supplementary counts")
    pending = manifest.loc[~manifest.query_id.isin(matched["query"])].copy()
    return manifest, matched, rejected, pending


def policy_statistics(frame: pd.DataFrame) -> list[dict]:
    """Reproduce the requested two-panel table without inventing runtimes.

    Policy defaults are a separate reporting convention, not observations. The
    measured-only report and plots never consume this synthetic speed-up column.
    """
    detail = plot.prepare_queries(frame, "tm")
    valid = detail.valid_timing.to_numpy()
    correct = frame.correct.astype(str).str.upper().eq("TRUE")
    defaults = (correct & frame.timing_status.eq("fallback-skip") &
                ~frame.note.fillna("").str.contains("TIMEOUT", case=False, regex=False))
    families = frame.family.map(plot.normalize_family)
    records = []
    for scope in ("all", "outeryan_selected"):
        scope_mask = pd.Series(True, index=frame.index)
        if scope == "outeryan_selected":
            scope_mask &= frame.selected_plan.eq("OUTERYAN")
        for family in FAMILY_ORDER:
            mask = scope_mask & (True if family == "All" else families.eq(family))
            measured = frame.loc[mask & valid]
            count_defaults = int((mask & defaults).sum())
            ratios = (measured.tm_off / measured.tm_on).tolist() + [1.0] * count_defaults
            distribution = plot.distribution(pd.Series(ratios, dtype=float))
            off, on = float(measured.tm_off.sum()), float(measured.tm_on.sum())
            records.append({
                "subset": scope, "family": family, "n": len(ratios),
                "measured": len(measured), "policy_defaults": count_defaults,
                **{key: distribution[key] for key in ("geomean", "mean", "median", "min", "max", "stddev")},
                "duckdb_total_s": off, "outeryan_total_s": on,
                "total_ratio": off / on if on > 0 else None,
            })
    return records


def benchmark_composition(frame: pd.DataFrame, population: str) -> dict:
    """Count one explicit cohort; keep pre-screen and reported counts separate."""
    result = plot.composition(frame)
    result["rule"] = COMPOSITION_RULE
    result["population"] = population
    result["provenance_counts"] = frame.provenance_class.value_counts().to_dict()
    return result


def replace_case_analysis(fragment: str, case_analysis: str | None) -> str:
    if case_analysis is None:
        return fragment
    heading = r"\subsubsection{Case Query Analysis}"
    if not case_analysis.strip().startswith(heading) or r"\fix{TODO}" in case_analysis:
        raise ValueError("Case analysis must start with its subsection heading and contain no TODO")
    placeholder = heading + "\n\n" + r"\fix{TODO}"
    if fragment.count(placeholder) != 1:
        raise ValueError("Expected exactly one Case Query Analysis placeholder")
    return fragment.replace(placeholder, case_analysis.strip())


def runtime_table_tex(rows: list[dict], minimum_speedup: float = 0.0) -> str:
    lines = [r"\begin{table}[t]", r"\centering\small\setlength{\tabcolsep}{6pt}",
             r"\begin{tabular}{lrrrrrr}", r"\toprule",
             r"Family & $n$ & Geomean & Mean & Median & Max & Total \\", r"\midrule"]
    for scope, title in (("all", "All valid queries"), ("outeryan_selected", "OuterYan-selected queries")):
        if scope != "all":
            lines.append(r"\midrule")
        lines.append(r"\multicolumn{7}{l}{\textit{" + title + r"}} \\")
        for row in rows:
            if row["subset"] != scope:
                continue
            cells = [plot.number(row["n"], 0)] + [plot.number(row[key]) for key in
                     ("geomean", "mean", "median", "max", "total_ratio")]
            lines.append(row["family"] + " & " + " & ".join(cells) + r" \\")
    all_row, selected = [row for row in rows if row["family"] == "All"]
    screen_note = ("Measured speed-ups below " + plot.factor(minimum_speedup) +
                   " are excluded by the reporting policy. " if minimum_speedup > 0 else "")
    lines += [r"\bottomrule", r"\end{tabular}",
              r"\caption{Statistics across benchmark workloads}", r"\label{tab:runtime-by-benchmark}",
              r"\par\smallskip\begin{minipage}{\linewidth}\footnotesize",
              screen_note + r"Measured pairs with both runtimes below $1$\,s are retained. "
              r"Timeouts and failed checks are excluded. Total is the ratio of measured runtime sums. "
              "The upper/lower panels include " + plot.number(all_row["measured"], 0) + "/" +
              plot.number(selected["measured"], 0) + " measured pairs and " +
              plot.number(all_row["policy_defaults"], 0) + "/" + plot.number(selected["policy_defaults"], 0) +
              r" unexecuted policy defaults of $1\times$; defaults are not measured speed-ups, "
              r"have no runtime, and do not enter Total. The text and figures use measured pairs only.",
              r"\end{minipage}", r"\end{table}"]
    return "\n".join(lines) + "\n"


def figure_includes_tex(measured_count: int, minimum_speedup: float) -> str:
    screen = ("Measured speed-ups below " + plot.factor(minimum_speedup) + " are excluded. "
              if minimum_speedup > 0 else "")
    overall = (
        "Runtime and speed-up comparison over " + plot.number(measured_count, 0)
        + " valid measured OuterYan-selected query instances. " + screen
        + r"Pairs with both runtimes below $1$\,s are retained; unexecuted policy defaults are not plotted."
    )
    phase = (
        "Execution breakdown and running-time comparison for representative queries from the same "
        "reporting subset. Left: normalized profiled CPU work; right: unprofiled running times. "
        "CPU work accumulates across threads and is not wall-clock time."
    )
    pieces = []
    for name, caption, label in (
        ("speedup_all_queries", overall, "fig:speedup-all-queries"),
        ("phase_breakdown_outeryan", phase, "fig:phase-breakdown"),
    ):
        pieces.append("\n".join([
            r"\begin{figure*}[t]", r"\centering",
            r"\includegraphics[width=\textwidth]{figures/" + name + ".pdf}",
            r"\caption{" + caption + "}", r"\label{" + label + "}", r"\end{figure*}",
        ]))
    return "\n\n".join(pieces) + "\n"


def pg_cases(manifest: pd.DataFrame, labels: pd.DataFrame) -> list[dict]:
    selected_path = HERE / "results/benchmark_pg_search_cpu8_20261003/selected-results.json"
    selected = json.loads(selected_path.read_text())
    records = []
    for key, default_case in (("job13193", "job12"), ("tpch8", "tpch8")):
        choice = selected[key]
        source = (selected_path.parent / choice["verified_results"]).resolve()
        result = json.loads(source.read_text())[choice.get("case", default_case)]
        rows = manifest.loc[manifest.path.eq(choice["query"])]
        if len(rows) != 1:
            raise ValueError(f"PG case no longer has an active benchmark counterpart: {key}")
        row = rows.iloc[0]
        if row.content_sha256 != result["query_file_sha256"]:
            raise ValueError(f"PG case SQL differs from the active definition: {key}")
        medians = {mode: float(pd.Series(result["runs"][mode]).median())
                   for mode in ("PG", "native", "OY")}
        ids = labels.loc[labels["query"].eq(row.query_id), "short_query"]
        records.append({
            "case": key, "query_id": row.query_id, "path": row.path,
            "short_query": ids.iloc[0] if len(ids) else row.query_id,
            "source_benchmark": row.source_benchmark, "source_query": row.source_query,
            "source_location": row.source_location, "tree_shape": row.tree_shape,
            "join_vector": row.join_vector, "relation_count": int(row.relation_count),
            "content_sha256": row.content_sha256, "exact_current_sql_match": True,
            "measurement_source": str(source), "measurement_sha256": digest(source),
            "runs_per_mode": {mode: len(result["runs"][mode]) for mode in medians},
            "median_ms": medians, "pg_speedup": medians["PG"] / medians["OY"],
            "native_speedup": medians["native"] / medians["OY"],
            "protocol": "cpu8, 1 thread, 4 GB, one warm-up, five-run median; TPC-H SF100",
        })
    return records


def fill_fragment(paper: dict, intro_n: int, pg: list[dict], corpus: dict | None = None,
                  policy_rows: list[dict] | None = None) -> str:
    groups = {row["family"]: row for row in paper["runtime"]["outeryan_selected"]}
    total = groups["All"]
    values = {
        "intro_n": plot.number(intro_n, 0),
        "selected_n": plot.number(total["counts"]["valid"], 0),
        "intro_gm": rf"\fix{{${total['speedup']['geomean']:.2f}\times$}}",
        "intro_max": rf"\fix{{${total['speedup']['max']:.1f}\times$}}",
        "overall_gm": plot.factor(total["speedup"]["geomean"]),
        "overall_max": plot.factor(total["speedup"]["max"]),
        "total_ratio": plot.factor(total["totals"]["speedup"]),
    }
    corpus = corpus or paper["input_corpus"]
    values["benchmark_sentence"] = (
        "The final benchmark contains " + plot.number(corpus["structural"], 0) +
        " structural queries and " + plot.number(corpus["supplementary"], 0) +
        " supplementary queries, for a total of " + plot.number(corpus["total"], 0) +
        " query instances. We report results by workload family, join-tree shape, join-graph topology, "
        "join-type composition, and selectivity level."
    )
    values["runtime_table"] = runtime_table_tex(
        policy_rows, paper.get("method", {}).get("reporting_minimum_speedup", 0.0)) if policy_rows else ""
    audit = paper.get("refresh_audit", {})
    values["cohort_note"] = ""
    if audit:
        values["cohort_note"] = (
            r"\paragraph{Reporting scope.} The benchmark count describes the reporting subset after excluding "
            + plot.number(audit["reporting_screened_rows"], 0) + " measured queries with speed-up below "
            + plot.factor(audit["reporting_minimum_speedup"]) + ". The original source corpus contains "
            + plot.number(audit["matched_queries"], 0) + " queries. The introductory statement covers "
            + plot.number(intro_n, 0) + " evaluable queries: "
            + plot.number(total["counts"]["valid"], 0) + " measured OuterYan plans and "
            + plot.number(audit["native_verified_fallback"], 0) + " verified native-plan fallbacks. "
            + "It excludes " + plot.number(audit["timeouts"], 0) + " timeouts and "
            + plot.number(audit["selected_but_untimed"], 0)
            + " queries marked as OuterYan-selected but skipped without measured runtimes. "
            + "The table separately includes these skipped queries as policy defaults, not measured speed-ups."
        )
    for family, code in zip(FAMILY_ORDER, ("graph", "tpch", "tpcds", "job", "all")):
        values[code + "_gm"] = plot.factor(groups[family]["speedup"]["geomean"])
        values[code + "_max"] = plot.factor(groups[family]["speedup"]["max"])
    phase_lines = []
    for row in paper["phase"]:
        label = "All" if row["family"] == "all" else row["family"]
        if label == "All":
            phase_lines.append(r"\midrule")
        fractions = row["cpu_weighted_fraction"]
        cells = [plot.number(row["profiles"], 0)]
        cells += [plot.number(100 * fractions[key], 2, r"\%") for key in PHASE_KEYS]
        phase_lines.append(label + " & " + " & ".join(cells) + r" \\")
    values["phase_rows"] = "\n".join(phase_lines)
    reps = paper["representatives"]
    below = sum(row["outeryan_optimizer_percent"] < 1 for row in reps)
    values["optimization_below"] = rf"\fix{{{below} of the {len(reps)} queries}}"
    values["optimization_max"] = plot.number(max(row["outeryan_optimizer_percent"] for row in reps), 2, r"\%")
    values["optimization_columns"] = "ll" + "r" * len(reps)
    values["optimization_header"] = "Category & Metric & " + " & ".join(row["short_query"] for row in reps) + r" \\"
    specifications = (
        ("Running Time (s)", "DuckDB", "duckdb_s", 3),
        ("", "OuterYan", "outeryan_s", 3),
        ("Query Statistics", r"\# Relations", "relation_count", 0),
        ("", r"\# Attributes", "attribute_count", 0),
        ("Optimization Time (ms)", "DuckDB", "duckdb_optimizer_ms", 3),
        ("", "OuterYan", "outeryan_optimizer_ms", 3),
        ("Optimization Ratio (\\%)", "DuckDB", "duckdb_optimizer_percent", 4),
        ("", "OuterYan", "outeryan_optimizer_percent", 4),
    )
    rows = []
    for index, (category, metric, field, precision) in enumerate(specifications):
        if index and category:
            rows.append(r"\midrule")
        prefix = rf"\multirow{{2}}{{*}}{{\textbf{{{category}}}}}" if category else ""
        rows.append(prefix + " & " + metric + " & " + " & ".join(
            plot.number(row[field], precision) for row in reps) + r" \\")
    values["optimization_rows"] = "\n".join(rows)
    for code, record in zip(("job", "tpch"), pg):
        values[f"pg_{code}_speedup"] = rf"\fix{{{record['pg_speedup']:.2f}$\times$}}"
        values[f"native_{code}_speedup"] = rf"\fix{{{record['native_speedup']:.2f}$\times$}}"
        for mode, name in (("PG", "pg"), ("native", "native"), ("OY", "oy")):
            values[f"{name}_{code}_ms"] = plot.number(record["median_ms"][mode], 2)
    job, tpch = pg
    values["pg_footnotes"] = (
        rf"\textsuperscript{{a}}Current benchmark query \texttt{{{job['short_query']}}}: "
        r"SQLStorm \texttt{v1.0/job/queries/13193.sql}-derived, "
        r"\fix{5} relations, right-deep, \texttt{L/F/R/I}, low-selectivity variant.\par" + "\n"
        rf"\textsuperscript{{b}}Current benchmark query \texttt{{{tpch['short_query']}}}: "
        r"TPC-H Q8-derived, \fix{6} relations, bushy, \texttt{F/R/I/F/L}, low-selectivity variant. "
        r"Both SQL files are byte-identical to their benchmark definitions; this table uses separate "
        r"\fix{1}-thread measurements (TPC-H \fix{SF100}), not the main \fix{32}-thread "
        r"measurements (TPC-H \fix{SF50})."
    )
    template = TEMPLATE.read_text()
    result = re.sub(r"@@([a-z_]+)@@", lambda match: values[match[1]], template)
    if "@@" in result:
        raise ValueError("Unexpanded manuscript placeholder")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="+", help="Original result CSVs; may include a later TPC-DS batch")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--samples-per-family", type=int, default=3)
    parser.add_argument("--no-figures", action="store_true", help="Statistics/template validation only")
    parser.add_argument("--replace-tpcds", type=Path,
                        help="Use only this TPC-DS batch; never carry forward missing old TPC-DS rows")
    parser.add_argument("--minimum-speedup", type=float, default=0.0,
                        help="Explicit reporting-only outcome screen; original CSVs and SQL remain intact")
    parser.add_argument("--case-analysis", type=Path,
                        help="Reviewed LaTeX subsection to replace the Case Query Analysis placeholder")
    args = parser.parse_args(argv)
    if args.samples_per_family < 1:
        parser.error("--samples-per-family must be positive")
    if not math.isfinite(args.minimum_speedup) or args.minimum_speedup < 0:
        parser.error("--minimum-speedup must be finite and nonnegative")
    if args.replace_tpcds and args.replace_tpcds.resolve() not in [Path(p).resolve() for p in args.csv]:
        parser.error("--replace-tpcds must also be listed as an input CSV")
    case_analysis = args.case_analysis.read_text() if args.case_analysis else None
    plot.MIN_RUNTIME_SECONDS = 0.0
    manifest, merged, rejected, pending = current_observations(args.csv, args.manifest, args.replace_tpcds)
    before = plot.prepare_queries(merged, "tm")
    screened = before.valid_timing.to_numpy() & (merged.tm_off / merged.tm_on).lt(args.minimum_speedup)
    screening_excluded = merged.loc[screened].copy()
    frame = merged.loc[~screened].reset_index(drop=True)
    source_corpus = benchmark_composition(merged, "Matched source corpus before reporting exclusions")
    corpus = benchmark_composition(frame, "Reporting subset after the explicit speed-up screen")
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = plot.build_statistics(frame, sources=args.csv)
    report["method"]["population"] = SCREENING
    report["method"]["reporting_minimum_speedup"] = args.minimum_speedup
    report["method"]["reporting_screened_rows"] = len(screening_excluded)
    report["method"]["excluded"] = (
        "Exact active-SQL intersection, followed by validity filtering. Historical outcome-based "
        "screening is recorded separately; fallback placeholders and timeouts are never imputed."
    )
    detail = plot.prepare_queries(frame, "tm")
    measured = detail.valid_timing.to_numpy()
    # A complete phase profile alone is not enough: require the same valid pair.
    report["phase_profiles"] = plot.build_phase_statistics(frame.loc[measured], "tm")
    paper = plot.build_paper_report(frame, report, args.samples_per_family)
    for key in ("corpus", "input_corpus"):
        paper[key]["rule"] = COMPOSITION_RULE
    policy_rows = policy_statistics(frame)
    paper["policy_runtime_table"] = policy_rows
    paper["complete_benchmark_composition"] = corpus
    paper["source_benchmark_composition"] = source_corpus
    labels = plot.add_short_query_labels(frame.loc[frame.selected_plan.eq("OUTERYAN")])
    pg = pg_cases(manifest, labels)
    native = (frame.selected_plan.eq("DUCKDB") & frame.correct.astype(str).str.upper().eq("TRUE")
              & frame.timing_status.eq("fallback-skip"))
    selected_valid = measured & frame.selected_plan.eq("OUTERYAN").to_numpy()
    selected_untimed = frame.selected_plan.eq("OUTERYAN") & frame.timing_status.eq("fallback-skip")
    intro_n = int(selected_valid.sum() + native.sum())
    audit = {
        "manifest": str(args.manifest.resolve()), "manifest_sha256": digest(args.manifest),
        "template_sha256": digest(TEMPLATE), "sources": report["sources"],
        "refresh_script_sha256": digest(Path(__file__)),
        "drawing_script_sha256": digest(Path(plot.__file__)),
        "active_queries": len(manifest), "matched_queries": len(merged), "reported_queries": len(frame),
        "reporting_minimum_speedup": args.minimum_speedup, "reporting_screened_rows": len(screening_excluded),
        "pending_queries": len(pending),
        "case_analysis_source": str(args.case_analysis.resolve()) if args.case_analysis else None,
        "case_analysis_sha256": digest(args.case_analysis) if args.case_analysis else None,
        "replace_tpcds_source": str(args.replace_tpcds.resolve()) if args.replace_tpcds else None,
        "rejected_observations": len(rejected), "source_runs": sorted(frame.source_run.unique()),
        "valid_measured_outeryan": int(selected_valid.sum()),
        "native_verified_fallback": int(native.sum()),
        "selected_but_untimed": int(selected_untimed.sum()),
        "timeouts": report["timeouts"]["total"],
        "intro_evaluable_cohort": intro_n,
        "both_subsecond_included": int((measured & frame.tm_off.lt(1) & frame.tm_on.lt(1)).sum()),
        "historical_screening": SCREENING,
        "intro_definition": "Valid measured OuterYan-selected pairs plus correctness-verified native-plan fallbacks; not the entire active manifest",
        "main_runtime_protocol": frame[["timing_threads", "timing_protocol", "timing_samples", "timing_estimator", "warmup_runs_per_side"]].drop_duplicates().to_dict("records"),
        "optimizer_measurement": "optimizer_*_total_s = all_optimizers; not just instrumented OuterYan workflow phases",
    }
    paper["refresh_audit"] = audit
    fragment = replace_case_analysis(fill_fragment(paper, intro_n, pg, corpus, policy_rows), case_analysis)
    (out / "paper_updates.tex").write_text(fragment)
    (out / "paper_replacements.tex").write_text(fragment.split(r"\subsubsection{Execution Breakdown}")[0])
    (out / "runtime_by_benchmark.tex").write_text(runtime_table_tex(policy_rows, args.minimum_speedup))
    (out / "figure_includes.tex").write_text(figure_includes_tex(int(selected_valid.sum()), args.minimum_speedup))
    write_json(out / "paper_statistics.json", paper)
    write_json(out / "statistics.json", report)
    write_json(out / "refresh_audit.json", audit)
    write_json(out / "pg_query_provenance.json", pg)
    frame.to_csv(out / "current_results.csv", index=False)
    merged.to_csv(out / "merged_current_results.csv", index=False)
    screening_excluded.to_csv(out / "reporting_excluded_speedup.csv", index=False)
    pd.DataFrame(policy_rows).to_csv(out / "policy_benchmark_statistics.csv", index=False)
    write_json(out / "benchmark_composition.json", corpus)
    write_json(out / "source_benchmark_composition.json", source_corpus)
    frame[["query", "family", "source_component", "provenance_class", "workload_component"]].to_csv(
        out / "benchmark_composition_queries.csv", index=False)
    pending.to_csv(out / "pending_queries.csv", index=False)
    rejected.to_csv(out / "excluded_observations.csv", index=False)
    labels.to_csv(out / "query_id_map.csv", index=False)
    frame.loc[selected_untimed].to_csv(out / "selected_but_untimed.csv", index=False)
    pd.DataFrame(paper["representatives"]).to_csv(out / "optimization_representatives.csv", index=False)
    pd.DataFrame(report["optimizer_profiles"]["queries"]).to_csv(out / "optimization_all_queries.csv", index=False)
    write_json(out / "optimization_workflow_phases.json", report["optimizer_profiles"]["phases"])
    phase_rows = [{"family": row["family"], "n": row["profiles"], "cpu_total_s": row["cpu_total_s"],
                   **{key + "_percent": 100 * row["cpu_weighted_fraction"][key] for key in PHASE_KEYS},
                   **{key + "_s": row["component_seconds"][key] for key in PHASE_KEYS}}
                  for row in paper["phase"]]
    pd.DataFrame(phase_rows).to_csv(out / "phase_summary.csv", index=False)
    pd.DataFrame(report["phase_profiles"]["queries"]).to_csv(out / "phase_all_queries.csv", index=False)
    stats = [{"subset": row["subset"], "family": row["family"], **row["counts"],
              **{key: row["speedup"][key] for key in ("min", "max", "geomean", "mean", "median", "stddev")},
              **row["totals"]}
             for row in report["groups"] if row["scope"] in ("overall", "benchmark")]
    pd.DataFrame(stats).to_csv(out / "benchmark_statistics.csv", index=False)
    pd.DataFrame(report["timeouts"]["distribution"]).to_csv(out / "timeout_summary.csv", index=False)
    pd.DataFrame(report["timeouts"]["queries"]).to_csv(out / "timeout_queries.csv", index=False)
    reps = paper["representatives"]
    highest = max(reps, key=lambda row: row["outeryan_optimizer_percent"])
    graph = next(row for row in phase_rows if row["family"] == "Graph")
    tpcds = next(row for row in stats if row["subset"] == "outeryan_selected" and row["family"] == "TPC-DS")
    review = f"""REVIEW BEFORE PUBLICATION — manuscript refresh

Population / denominator
Active manifest: {len(manifest)}; matching result rows: {len(merged)}; pending: {len(pending)}.
Reporting-only speed-up cutoff: {args.minimum_speedup}; excludes {len(screening_excluded)} measured rows.
The benchmark composition sentence counts {corpus['total']} queries AFTER reporting exclusions.
The original source corpus has {source_corpus['total']} queries; source_benchmark_composition.json preserves its counts.
The original 20261002 CSV remains immutable. merged_current_results.csv has all current SQL matches,
with the TPC-DS family fully replaced when --replace-tpcds is supplied. current_results.csv is the
reporting cohort AFTER any explicit speed-up screen. Neither command changes SQL definitions.
Intro: {intro_n} = {int(selected_valid.sum())} measured OuterYan pairs + {int(native.sum())} verified native-plan fallbacks.
The intro is an evaluable subset, NOT all active queries. The unchanged sentence cannot safely use
the full manifest as denominator: {audit['timeouts']} timeout rows, {int(selected_untimed.sum())} selected-but-untimed
rows and {len(pending)} pending rows are excluded. Review this scope before copying the sentence.
Headline speed-up statistics use only the {int(selected_valid.sum())} measured selected pairs.
Both runtimes <1s: {audit['both_subsecond_included']} retained.
The requested two-panel table additionally reports clearly labeled policy defaults of 1x in its
distribution statistics. These are NOT observations and do NOT enter runtime sums or the figures.
The table's lower-panel geomean therefore differs from the measured-only headline. See table notes
and policy_benchmark_statistics.csv. benchmark_statistics.csv remains measured-only.
{SCREENING}

Unchanged statements requiring review (not silently rewritten)
1. Overall: TPC-DS geometric mean is now {tpcds['geomean']:.4f}x ({tpcds['valid']} valid measured queries).
   'Substantial speedups' describes the aggregate only, not every query or a statistical significance test.
2. Graph: 'most execution work remains in Round 3' conflicts with weighted CPU shares:
   R3 = {graph['round3_percent']:.2f}%, Other = {graph['other_percent']:.2f}%.
3. H-RD-03 is an old identifier, not a query ID in this refreshed sample. The assertion about its
   limited pruning needs a separately verified case; no causal claim is inferred from time shares.
4. Optimization: 'runtime medians' is stale for the main experiment: timing_samples=1,
   timing_estimator=single_post_warmup, warmup_runs_per_side=2. PG uses separate five-run medians.
5. Optimization: the table uses all_optimizers totals per configuration. The paragraph saying
   'all OuterYan optimization steps' is narrower. Workflow phase measurements are separately
   exported in optimization_workflow_phases.json; they are not substituted for total optimizer time.
6. Optimization: 'negligible ... savings' is not uniformly supported. {highest['short_query']} has
   {highest['outeryan_optimizer_ms']:.3f} ms total optimization / {highest['outeryan_s']:.6f} s runtime
   = {highest['outeryan_optimizer_percent']:.2f}%; some representatives are slower than DuckDB.
7. Case Query Analysis: {'reviewed subsection included from ' + str(args.case_analysis) if args.case_analysis else 'supplied TODO retained; no case-analysis source supplied'}.

Fallback recording issue (no harness/optimizer changes made)
{int(selected_untimed.sum())} rows say selected_plan=OUTERYAN but timing_status=fallback-skip.
The current harness skips any aggregate with aggregate_pushdown_applied=0 even if OuterYan is
selected. These rows are NOT established native-plan fallbacks and are NOT measured speed-ups.
See selected_but_untimed.csv. Their trace flags are preserved rather than relabeled.

Figures and representative selection
All valid measured pairs are plotted, including sub-second pairs. No timeout coordinates are invented.
Phase figure and optimization table use up to {args.samples_per_family} queries per family:
shape quotas, then evenly spaced DuckDB-runtime ranks, without speed-up ranking.
Phase-summary table uses ALL valid complete selected profiles, not only the figure's sample.
Percentages are sum(phase CPU seconds) / sum(total CPU seconds); CPU seconds are not wall time.
Full-precision times drive all ratios; displayed numbers are rounded only at formatting.
Footnotes map both PG examples to byte-identical current SQL and original source paths in
pg_query_provenance.json. PG measurements remain separate (cpu8, 1 thread, TPC-H SF100).

Refresh after new TPC-DS results arrive
Pass the original full CSV AND the new TPC-DS CSV to auto_test/refresh_paper_results.py.
Latest exact-SQL observation wins, including failure/timeout; incompatible per-family environments
are rejected. Use a new --output-dir to retain this snapshot. Source hashes are in refresh_audit.json.
"""
    (out / "REVIEW.txt").write_text(review)
    command = ["python3", str(Path(__file__).resolve()), *[str(Path(path).resolve()) for path in args.csv],
               "--manifest", str(args.manifest.resolve()), "--output-dir", str(out),
               "--samples-per-family", str(args.samples_per_family),
               "--minimum-speedup", str(args.minimum_speedup)]
    if args.replace_tpcds:
        command += ["--replace-tpcds", str(args.replace_tpcds.resolve())]
    if args.case_analysis:
        command += ["--case-analysis", str(args.case_analysis.resolve())]
    (out / "REPRODUCE.txt").write_text(
        "Regenerate this snapshot (statistics, LaTeX and both figures):\n\n"
        + shlex.join(command) + "\n\n"
        "After the TPC-DS rerun, append its CSV after the existing CSV argument(s) and use a new "
        "--output-dir. Do not replace the existing full-run CSV with a TPC-DS-only CSV. "
        "The latest matching SQL result, including failure, replaces the old observation.\n"
    )
    if not args.no_figures:
        plot._load_plotting()
        plot.write_standalone_runtime_figures(out / "figures", frame, "active_manifest_refresh", "tm",
                                             sample_per_family=args.samples_per_family)
    print(json.dumps(audit, indent=2))
    print(f"Paper fragment and figures: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
