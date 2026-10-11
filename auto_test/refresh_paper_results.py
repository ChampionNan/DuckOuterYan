#!/usr/bin/env python3
"""Refresh manuscript statistics and figures against the active SQL manifest.

Pass a new complete-run CSV alone, or combine a previous snapshot with a later
partial rerun. The latest identical-SQL observation wins, including failures.
No queries run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
    "source_connected_subgraph": "structural",
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
    "retires 7 measured TPC-DS speed-ups below 0.5. Later frozen exact-SQL screening rules "
    "and their family counts are recorded under active_performance_screens. "
    "Not an unbiased benchmark sample. Remaining sub-second pairs are retained. "
    "No new speed-up cutoff is applied by this report."
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def active_performance_screens(manifest_path: Path) -> list[dict]:
    """Disclose the frozen rules actually attached to the current manifest."""
    marker_path = manifest_path.parent / "speedup_screen.json"
    marker = json.loads(marker_path.read_text()) if marker_path.exists() else {}
    counts = marker.get("rule_removed_counts", {})
    rules = [dict(rule_id=rule_id, **rule, removed_by_family=counts.get(rule_id, {}))
             for rule_id, rule in marker.get("rules", {}).items()]
    if (manifest_path.parent / "retirements.json").exists():
        import benchmark_retirements
        from collections import Counter
        spec = benchmark_retirements.policy()
        rules.append(dict(rule_id=spec["revision"], threshold=spec["threshold"], inclusive=spec["inclusive"],
                          removed_by_family=dict(Counter(r["family"] for r in spec["excluded"])),
                          selection=spec.get("selection", "Frozen exact-SQL removals")))
    return rules


def screening_disclosure_tex(screens: list[dict]) -> str:
    """Performance-conditioned sample changes are not optimizer improvements."""
    sentences = []
    for rule in screens:
        counts = rule.get("removed_by_family", {})
        if not counts:
            continue
        families = sorted(counts, key=lambda family: FAMILY_ORDER.index(plot.normalize_family(family)))
        items = [plot.number(counts[family], 0) + " " + plot.normalize_family(family)
                 for family in families]
        scope = " and ".join(items) if len(items) <= 2 else ", ".join(items[:-1]) + ", and " + items[-1]
        comparison = "at most " if rule.get("inclusive") else "below "
        threshold = rf"\fix{{${rule['threshold']:g}\times$}}"
        sentences.append("A frozen performance-screening rule excludes " + scope +
                         " query instances whose observed speed-ups were " + comparison + threshold + ".")
    if not sentences:
        return ""
    return (" " + " ".join(sentences) +
            " These exclusions change the reported workload rather than the optimizer's "
            "performance on unchanged queries.")


def output_directory(frame: pd.DataFrame, override: Path | None = None) -> Path:
    """Keep merged refreshes under the latest contributing experiment date."""
    if override is not None:
        return override.expanduser().resolve()
    dates = frame.source_run.astype(str).str[:8]
    if dates.empty or not dates.str.fullmatch(r"\d{8}").all():
        raise ValueError("CSV group has no date; supply --output-dir for custom inputs")
    return plot.DEFAULT_OUTPUT_ROOT / dates.max()


def refresh_scope(frame: pd.DataFrame, active_queries: int, pending_queries: int) -> str:
    """Describe observed run coverage without inferring optimizer revisions."""
    if frame.source_run.nunique() == 1:
        if pending_queries == 0 and len(frame) == active_queries:
            return (
                "One complete source run covers the full active SQL manifest. All current statuses "
                "and measurements come from that run; no earlier measurements are carried forward. "
                "Full coverage does not imply that every query has a measured runtime pair."
            )
        return (
            "One partial source run supplies the matching active-SQL observations. Missing manifest "
            "queries remain pending; no earlier measurements are carried forward."
        )
    return (
        "Latest exact-SQL observation per query across multiple source runs. Partial reruns replace "
        "only their matching queries; other queries retain earlier observations. This is a "
        "composite snapshot, not a single complete-run measurement. Source-run dates alone do not "
        "establish whether optimizer revisions differ."
    )


def correctness_scope_tex(audit: dict) -> str:
    """Keep runtime validity distinct from result-equivalence verification."""
    unchecked = int(audit.get("measured_correctness_disabled", 0))
    verified = int(audit.get("measured_verified", 0))
    if not unchecked:
        return ""
    if not verified:
        return (
            " Correctness checking was disabled for these performance-only measurements. Here, valid "
            "measurements mean complete positive paired runtimes, not result-equivalence verification."
        )
    return (
        " This reporting subset includes " + plot.number(unchecked, 0)
        + " performance-only pairs with correctness checking disabled and " + plot.number(verified, 0)
        + " pairs with passed correctness checks. Runtime validity is distinct from "
        "result-equivalence verification."
    )


def database_signature(path: str, size_bytes: int, mtime_ns: int) -> str:
    """Reproduce the harness's path/stat signature, not a database-content hash."""
    payload = json.dumps([path, size_bytes, mtime_ns], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def canonical_database_signatures(frame: pd.DataFrame, evidence: list[dict]) -> pd.Series:
    """Allow only explicitly audited renames; preserve every original signature."""
    canonical = frame.database_signature.copy()
    seen = set()
    for record in evidence:
        family, host = plot.normalize_family(record["family"]), record["execution_host"]
        size, mtime = record["size_bytes"], record["mtime_ns"]
        if type(size) is not int or type(mtime) is not int or size <= 0 or mtime < 0:
            raise ValueError("Database rename evidence requires positive size and integer mtime_ns")
        for side in ("old", "new"):
            path, signature = record[f"{side}_path"], record[f"{side}_signature"]
            if not Path(path).is_absolute() or database_signature(path, size, mtime) != signature:
                raise ValueError(f"Invalid {side} database rename signature")
            if signature in seen:
                raise ValueError("Database rename evidence has duplicate/ambiguous signatures")
            seen.add(signature)
            matching = frame.database_signature.eq(signature)
            environment = frame.family.map(plot.normalize_family).eq(family) & frame.execution_host.eq(host)
            if (matching & ~environment).any():
                raise ValueError("Database rename evidence does not match the recorded family/host")
            canonical.loc[matching] = record["new_signature"]
    return canonical


def current_observations(sources: list[str], manifest_path: Path, replace_tpcds: Path | None = None,
                         database_renames: list[dict] | None = None):
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
        if replacement.source_run.nunique() != 1:
            raise ValueError("TPC-DS replacement must identify one source run")
        # This is a complete family snapshot at its date, not a restriction on
        # future updates. Later partial runs replace only their matching SQL.
        replaced = (loaded.family.map(plot.normalize_family).eq("TPC-DS")
                    & loaded.source_run.lt(replacement.source_run.iloc[0]))
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
    older = matched.duplicated("sql_identity", keep="last")
    superseded_rows = matched.loc[older].copy()
    superseded_rows["refresh_exclusion"] = "superseded_exact_sql_observation"
    rejected = pd.concat([rejected, superseded_rows], ignore_index=True)
    matched = matched.loc[~older].reset_index(drop=True)
    if matched.empty:
        raise ValueError("No exact active-SQL measurements found")
    if database_renames:
        matched["database_canonical_signature"] = canonical_database_signatures(matched, database_renames)
    signature_column = "database_canonical_signature" if database_renames else "database_signature"
    # Dataset-qualified Graph queries deliberately use two different databases.
    # Keep host/protocol checks family-wide; relax only the DB-signature grouping.
    graph_rows = matched.family.map(plot.normalize_family).eq("Graph")
    expected_datasets = matched["query"].map(active.get("graph_dataset", pd.Series(dtype=str))).fillna("")
    expected_datasets.loc[graph_rows & expected_datasets.eq("")] = "bitcoin"
    recorded_datasets = matched.get("graph_dataset", pd.Series("", index=matched.index)).fillna("")
    if (graph_rows & recorded_datasets.ne("") & recorded_datasets.ne(expected_datasets)).any():
        raise ValueError("Recorded Graph dataset does not match the active manifest")
    matched["graph_dataset"] = expected_datasets.where(graph_rows, "")
    for family, rows in matched.groupby("family"):
        for column in ("timing_threads", "execution_host",
                       "timing_protocol", "timing_samples", "timing_estimator"):
            if column in rows and rows[column].nunique(dropna=False) != 1:
                raise ValueError(f"Incompatible {column} in {family}; do not pool these experiments")
        for dataset, group in rows.groupby("graph_dataset", dropna=False):
            if signature_column in group and group[signature_column].nunique(dropna=False) != 1:
                raise ValueError(f"Incompatible {signature_column} in {family}/{dataset}; do not pool these experiments")
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


def apply_timeout_substitution(frame: pd.DataFrame, seconds: int = 0) -> pd.DataFrame:
    """Compatibility entry point: preserve raw times; timeout imputation is retired."""
    if seconds != 0:
        raise ValueError("Timeout substitution is retired: exclude a query if either engine times out")
    result = frame.copy()
    result["recorded_tm_off"] = frame.tm_off
    result["recorded_tm_on"] = frame.tm_on
    result["runtime_treatment"] = "not-measured"
    result.loc[plot.prepare_queries(frame, "tm").valid_timing.to_numpy(), "runtime_treatment"] = "measured"
    result.loc[plot.timeout_mask(frame), "runtime_treatment"] = "excluded_timeout"
    return result


def reporting_cohort(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One cohort for figures, table and prose; exact 1x is not rounded 1.000x."""
    detail = plot.prepare_queries(frame, "tm")
    reasons = detail.exclusion_reason.copy()
    valid = detail.valid_timing
    measured_status = frame.timing_status.astype(str).str.lower().eq("measured").to_numpy()
    reasons.loc[valid & ~measured_status] = "timing_status_not_measured"
    selected = detail.selected_plan.eq("OUTERYAN")
    reasons.loc[valid & measured_status & ~selected] = "not_outeryan_selected"
    reasons.loc[valid & measured_status & selected & detail.speedup.eq(1.0)] = "exact_unit_speedup"
    eligible = reasons.eq("").to_numpy()
    excluded = frame.loc[~eligible].copy()
    excluded["reporting_exclusion"] = reasons.loc[~eligible].to_numpy()
    return frame.loc[eligible].reset_index(drop=True), excluded


def policy_statistics(frame: pd.DataFrame) -> list[dict]:
    """Single measured-selected table. No skipped-query 1x imputation."""
    measured, _ = reporting_cohort(frame)
    families = measured.family.map(plot.normalize_family)
    records = []
    for family in FAMILY_ORDER:
        rows = measured if family == "All" else measured.loc[families.eq(family)]
        ratios = rows.tm_off / rows.tm_on
        distribution = plot.distribution(ratios)
        off, on = float(rows.tm_off.sum()), float(rows.tm_on.sum())
        records.append({
            "subset": "outeryan_selected", "family": family, "n": len(rows),
            "measured": int((~plot.timeout_substitution_mask(rows)).sum()), "policy_defaults": 0,
            "timeout_substituted": int(plot.timeout_substitution_mask(rows).sum()),
            **{key: distribution[key] for key in ("geomean", "mean", "median", "min", "max", "stddev")},
            "duckdb_total_s": off, "outeryan_total_s": on,
            "total_ratio": off / on if on > 0 else None,
        })
    return records


def replacement_audit(merged: pd.DataFrame, rejected: pd.DataFrame) -> pd.DataFrame:
    """Show the latest superseded exact-SQL result beside its replacement."""
    older = rejected.loc[rejected.refresh_exclusion.eq("superseded_exact_sql_observation")]
    older = older.sort_values(["source_run", "source_csv"], kind="stable").drop_duplicates(
        "sql_identity", keep="last")
    columns = [column for column in (
        "sql_identity", "query", "family", "sql_content_sha256", "source_run", "source_csv",
        "correct", "timing_status", "selected_plan", "tm_off", "tm_on", "database_signature",
    ) if column in merged and column in older]
    pairs = older[columns].merge(merged[columns], on="sql_identity", suffixes=("_old", "_new"),
                                 validate="one_to_one")
    for side in ("old", "new"):
        off, on = pd.to_numeric(pairs[f"tm_off_{side}"], errors="coerce"), pd.to_numeric(
            pairs[f"tm_on_{side}"], errors="coerce")
        ratio = off / on
        pairs[f"speedup_{side}"] = ratio.where(off.gt(0) & on.gt(0) & ratio.lt(float("inf")))
    return pairs


def export_runtime_data(out, manifest, merged, reporting_view, labels):
    """Full active coverage; only complete eligible pairs get a reported speed-up."""
    raw = merged.set_index("query")
    view = reporting_view.set_index("query")
    ids = labels.set_index("query").short_query.to_dict()
    cohort, _ = reporting_cohort(reporting_view)
    eligible_queries = set(cohort["query"])
    timed_out_queries = set(merged.loc[plot.timeout_mask(merged), "query"])
    details = []
    for _, item in manifest.iterrows():
        query = item.query_id
        row = raw.loc[query] if query in raw.index else pd.Series(dtype=object)
        report = view.loc[query] if query in view.index else pd.Series(dtype=object)
        off, on = row.get("tm_off", float("nan")), row.get("tm_on", float("nan"))
        pair = query in eligible_queries
        treatment = report.get("runtime_treatment", "unavailable")
        details.append(dict(
            family=plot.normalize_family(item.family), graph_dataset=item.get("graph_dataset", ""),
            query=query, reference_query_label=ids.get(query, ""),
            replaces_query=item.get("graph_dataset_source_query", ""),
            selected_plan=row.get("selected_plan", ""), aggregate_query=int(item.query_class == "aggregate"),
            aggregate_pushdown_applied=row.get("aggregate_pushdown_applied", ""),
            tree_shape=item.tree_shape, selectivity_tier=item.semantic_tier,
            timing_status=row.get("timing_status", "pending"),
            duckdb_status=row.get("duckdb_status", "pending"), outeryan_status=row.get("outeryan_status", "pending"),
            duckdb_s=off, outeryan_s=on, measured_speedup=off / on if pair else None,
            complete_selected_pair=pair, runtime_treatment=treatment,
            reported_duckdb_s=off if pair else None,
            reported_speedup=off / on if pair else None,
            excluded_timeout=query in timed_out_queries,
            duckdb_timeout_stage=row.get("duckdb_timeout_stage", ""),
            outeryan_timeout_stage=row.get("outeryan_timeout_stage", ""),
            source_run=row.get("source_run", ""), sql_content_sha256=item.content_sha256,
            **{f"both_le_{threshold:g}s": bool(pair and off <= threshold and on <= threshold)
               for threshold in (.1, .5, 1)}))
    data = pd.DataFrame(details)
    data.to_csv(out / "runtime_query_times.csv", index=False)
    data.loc[data.family.eq("Graph")].to_csv(out / "graph_query_times.csv", index=False)
    bins = [0, .01, .05, .1, .5, 1, 10, 60, 600, float("inf")]
    distribution = []
    for family in FAMILY_ORDER:
        group = data if family == "All" else data.loc[data.family.eq(family)]
        for scope in ("complete_selected_pairs", "all_measured_engine_sides"):
            for engine, column in (("DuckDB", "duckdb_s"), ("OuterYan", "outeryan_s")):
                eligible = group.loc[group.complete_selected_pair] if scope == "complete_selected_pairs" else group.loc[
                    group["duckdb_status" if engine == "DuckDB" else "outeryan_status"].eq("measured")]
                values = pd.to_numeric(eligible[column], errors="coerce").dropna()
                for lower, upper in zip(bins, bins[1:]):
                    distribution.append(dict(family=family, scope=scope, engine=engine,
                                             lower_exclusive_s=lower, upper_inclusive_s=upper,
                                             queries=int((values.gt(lower) & values.le(upper)).sum()),
                                             measured_queries=len(values)))
    pd.DataFrame(distribution).to_csv(out / "runtime_distribution.csv", index=False)
    (out / "RUNTIME_DISTRIBUTION_ANALYSIS.txt").write_text(
        f"Active queries: {len(data)}; complete measured selected pairs: {int(data.complete_selected_pair.sum())}; "
        f"timeout substitutions: {int(data.runtime_treatment.eq('duckdb_timeout_600s').sum())}; "
        f"pending: {int(data.timing_status.eq('pending').sum())}.\n"
        "Performance statistics use complete non-timeout selected pairs only, with no timeout substitution. "
        "The all_measured_engine_sides bins are coverage diagnostics, not the performance cohort.\n")


def benchmark_composition(frame: pd.DataFrame, population: str) -> dict:
    """Count one explicit cohort; keep pre-screen and reported counts separate."""
    result = plot.composition(frame)
    result["rule"] = COMPOSITION_RULE
    result["population"] = population
    result["provenance_counts"] = frame.provenance_class.value_counts().to_dict()
    return result


def query_distribution(manifest: pd.DataFrame, measured: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Count SQL query types and input shapes, independent of pushdown decisions."""
    if manifest.query_id.isna().any() or manifest.query_id.duplicated().any():
        raise ValueError("Distribution requires unique manifest query IDs")
    measured_ids = measured["query"]
    if measured_ids.isna().any() or measured_ids.duplicated().any():
        raise ValueError("Distribution requires unique measured query IDs")
    if not set(measured_ids).issubset(set(manifest.query_id)):
        raise ValueError("Measured query is absent from the active manifest")
    data = manifest[["query_id", "family", "tree_shape", "aggregate_variant", "query_class"]].copy()
    data["family"] = data.family.map(plot.normalize_family)
    shapes = ("left_deep", "right_deep", "bushy")
    data["tree_shape"] = data.tree_shape.str.replace("-", "_", regex=False)
    if not data.tree_shape.isin(shapes).all() or not data.family.isin(FAMILY_ORDER[:-1]).all():
        raise ValueError("Unrecognized family or input tree shape in manifest")
    aggregate = data.aggregate_variant.fillna("").str.strip().ne("")
    if not data.query_class.isin(("join", "graph", "aggregate")).all() or not aggregate.eq(data.query_class.eq("aggregate")).all():
        raise ValueError("Manifest aggregate variant and query class disagree")
    data["query_type"] = aggregate.map({True: "aggregation", False: "full"})
    summaries, cross_counts = [], []
    for cohort, population in (("active_benchmark", data),
                               ("measured_outeryan", data.loc[data.query_id.isin(measured_ids)])):
        for family in FAMILY_ORDER:
            group = population if family == "All" else population.loc[population.family.eq(family)]
            summary = dict(cohort=cohort, family=family, total=len(group),
                           full_queries=int(group.query_type.eq("full").sum()),
                           aggregation_queries=int(group.query_type.eq("aggregation").sum()))
            summary.update({shape: int(group.tree_shape.eq(shape).sum()) for shape in shapes})
            summaries.append(summary)
            for kind in ("full", "aggregation"):
                for shape in shapes:
                    cross_counts.append(dict(cohort=cohort, family=family, query_type=kind, tree_shape=shape,
                                             n=int((group.query_type.eq(kind) & group.tree_shape.eq(shape)).sum())))
    return summaries, cross_counts


def query_distribution_tex(rows: list[dict]) -> str:
    lines = [r"\begin{table}[t]", r"\centering\small\setlength{\tabcolsep}{4pt}",
             r"\caption{Query distribution by workload family, query type, and input tree shape.}",
             r"\label{tab:query-distribution}", r"\begin{tabular}{lrrrrrr}", r"\toprule",
             r" & & \multicolumn{2}{c}{Query type} & \multicolumn{3}{c}{Tree shape} \\",
             r"\cmidrule(lr){3-4}\cmidrule(lr){5-7}",
             r"Family & $n$ & Full & Agg. & LD & RD & Bushy \\", r"\midrule"]
    fields = ("total", "full_queries", "aggregation_queries", "left_deep", "right_deep", "bushy")
    for index, (cohort, title) in enumerate((("active_benchmark", "All benchmark queries"),
                                             ("measured_outeryan", "Valid measured OuterYan-selected queries"))):
        if index:
            lines.append(r"\midrule")
        lines.append(r"\multicolumn{7}{l}{\textit{" + title + r"}} \\")
        for row in rows:
            if row["cohort"] == cohort:
                lines.append(row["family"] + " & " + " & ".join(plot.number(row[key], 0) for key in fields) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines) + "\n"


def query_distribution_discussion_tex(rows: list[dict]) -> str:
    totals = {row["cohort"]: row for row in rows if row["family"] == "All"}
    active, measured = totals["active_benchmark"], totals["measured_outeryan"]
    def count(row, key):
        return plot.number(row[key], 0)
    def share(row, key):
        return plot.number(100 * row[key] / row["total"], 2, r"\%") if row["total"] else plot.number(None)
    text = (
        r"Table~\ref{tab:query-distribution} reports the query distribution. "
        "Full denotes non-aggregation queries, not queries composed exclusively of FULL OUTER JOINs; "
        "Agg. denotes aggregation queries regardless of whether aggregation is pushed down. "
        "LD and RD denote left-deep and right-deep input join expressions. "
        "The benchmark contains " + count(active, "full_queries") + " full queries (" + share(active, "full_queries") +
        ") and " + count(active, "aggregation_queries") + " aggregation queries (" + share(active, "aggregation_queries") +
        "). Its left-deep, right-deep, and bushy expressions number " + count(active, "left_deep") + ", " +
        count(active, "right_deep") + ", and " + count(active, "bushy") + ", respectively.\n\n"
        "The valid measured OuterYan-selected subset contains " + count(measured, "full_queries") + " full queries and " +
        count(measured, "aggregation_queries") + " aggregation queries; its corresponding shape counts are " +
        count(measured, "left_deep") + ", " + count(measured, "right_deep") + ", and " + count(measured, "bushy") +
        ". Aggregation queries account for " + share(measured, "aggregation_queries") +
        " of this measured subset. The shape counts describe the input expressions, not the physical plans selected by the optimizer.\n"
    )
    families = [row for row in rows if row["cohort"] == "measured_outeryan"
                and row["family"] != "All" and row["total"]]
    if families:
        largest = max(families, key=lambda row: row["aggregation_queries"] / row["total"])
        text += ("\n" + largest["family"] + " has the largest aggregation share among the measured workload families: " +
                 count(largest, "aggregation_queries") + " of " + count(largest, "total") + " queries (" +
                 share(largest, "aggregation_queries") + "). ")
        active_families = {row["family"]: row for row in rows if row["cohort"] == "active_benchmark"}
        for row in families:
            for shape in ("left_deep", "right_deep", "bushy"):
                available = active_families[row["family"]]
                if available[shape] and not row[shape]:
                    text += (row["family"] + " contains " + count(available, shape) + " " +
                             shape.replace("_", "-") + " queries in the full benchmark, but none in the "
                             "valid measured OuterYan-selected subset. ")
        text = text.rstrip() + "\n"
    return text


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
    if any(row.get("timeout_substituted", 0) for row in rows):
        raise ValueError("Performance tables require complete non-timeout measured pairs")
    lines = [r"\begin{table}[t]", r"\centering\small\setlength{\tabcolsep}{6pt}",
             r"\begin{tabular}{lrrrrr}", r"\toprule",
             r"Family & $n$ & Geomean & Median & Max & Total \\", r"\midrule"]
    for row in rows:
        if row["subset"] != "outeryan_selected":
            continue
        cells = [plot.number(row["n"], 0)] + [plot.number(row[key]) for key in
                 ("geomean", "median", "max", "total_ratio")]
        lines.append(row["family"] + " & " + " & ".join(cells) + r" \\")
    selected = next(row for row in rows if row["family"] == "All" and row["subset"] == "outeryan_selected")
    note = (
        "The table, overall analysis and runtime figure use the same " +
        plot.number(selected["measured"], 0) + " valid measured OuterYan-selected pairs. "
        r"Pairs with both runtimes below $1$\,s are retained. Any timeout on either engine, failed checks, "
        r"unexecuted fallback defaults and exact $1\times$ ratios are excluded. "
        r"No default ratios are imputed. Total is the ratio of measured runtime sums.")
    lines += [r"\bottomrule", r"\end{tabular}",
              r"\caption{Statistics across benchmark workloads}", r"\label{tab:runtime-by-benchmark}",
              r"\par\smallskip\begin{minipage}{\linewidth}\footnotesize",
              note,
              r"\end{minipage}", r"\end{table}"]
    return "\n".join(lines) + "\n"


def figure_includes_tex(measured_count: int, minimum_speedup: float, substitutions: int = 0) -> str:
    if substitutions:
        raise ValueError("Figures exclude every query with a timeout on either engine")
    overall = (
        "Runtime and speed-up comparison over " + plot.number(measured_count, 0)
        + " valid measured OuterYan-selected query instances, matching the performance table and text. "
        + r"Pairs with both runtimes below $1$\,s are retained. Any timeout on either engine is excluded; unexecuted policy defaults "
        r"and exact $1\times$ ratios are not plotted."
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
            r"\includegraphics[width=\textwidth]{" + name + ".pdf}",
            r"\caption{" + caption + "}", r"\label{" + label + "}", r"\end{figure*}",
        ]))
    return "\n\n".join(pieces) + "\n"


def phase_discussion_tex(groups: list[dict]) -> str:
    families = {plot.normalize_family(row["family"]): row for row in groups}

    def share(family: str, *components: str) -> str:
        fractions = families[family]["cpu_weighted_fraction"]
        return plot.number(100 * sum(fractions[key] for key in components), 2, r"\%")

    return (
        "The execution breakdown differs across workloads. For Graph, the remaining operators "
        "account for " + share("Graph", "other") + " of profiled CPU work, compared with "
        + share("Graph", "round3") + " for Round~3 and " + share("Graph", "round1", "round2")
        + " for the two semi-join rounds combined. Round~3 accounts for "
        + share("TPC-H", "round3") + " and " + share("JOB", "round3")
        + " in TPC-H and JOB, respectively. For TPC-DS, the two semi-join rounds account for "
        + share("TPC-DS", "round1", "round2") + ", while Round~3 accounts for "
        + share("TPC-DS", "round3") + ". Across all retained profiles, the two semi-join rounds, "
        "Round~3, and the remaining operators account for " + share("all", "round1", "round2")
        + ", " + share("all", "round3") + ", and " + share("all", "other") + ", respectively.\n\n"
        "These percentages describe work within the selected OuterYan plans. A large semi-join "
        "share does not by itself imply a slowdown, nor does a small Round~3 share quantify the "
        "join work saved relative to DuckDB. End-to-end performance must be assessed using the "
        "paired running times in the right panel; isolating the contribution of semi-join "
        "reduction requires a separate ablation."
    )


def optimization_discussion_tex(reps: list[dict]) -> str:
    below = sum(row["outeryan_optimizer_percent"] < 1 for row in reps)
    highest = max(reps, key=lambda row: row["outeryan_optimizer_percent"])

    def interval(field: str) -> str:
        return (plot.number(min(row[field] for row in reps), 3) + "--"
                + plot.number(max(row[field] for row in reps), 3) + r"\,ms")

    overhead = [row["outeryan_optimizer_ms"] - row["duckdb_optimizer_ms"] for row in reps]
    return (
        r"Table~\ref{tab:optimization-time} shows an OuterYan optimization ratio below \fix{1\%} for "
        + rf"\fix{{{below} of the {len(reps)} queries}}" + ", with a maximum of "
        + plot.number(highest["outeryan_optimizer_percent"], 2, r"\%") + ". Total optimization time "
        "ranges from " + interval("duckdb_optimizer_ms") + " for DuckDB and "
        + interval("outeryan_optimizer_ms") + " with OuterYan enabled. The difference between "
        "the enabled and disabled configurations ranges from " + plot.number(min(overhead), 3)
        + " to " + plot.number(max(overhead), 3) + r"\,ms. The largest relative cost occurs for "
        + r"\texttt{" + plot.latex_escape(highest["short_query"]) + "}, whose "
        + plot.number(highest["outeryan_optimizer_ms"], 3) + r"\,ms of optimization is compared with "
        + plot.number(1000 * highest["outeryan_s"], 3) + r"\,ms of unprofiled running time. "
        "The absolute optimization-time difference is therefore small for these representatives, "
        "but its relative cost is not uniformly negligible for short-running queries."
    )


def execution_optimization_sections(fragment: str) -> str:
    start = fragment.index(r"\subsubsection{Execution Breakdown}")
    end = fragment.index(r"\subsubsection{PostgreSQL Plan Comparison}", start)
    return fragment[start:end].rstrip() + "\n"


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


def pg_footnotes_tex(pg: list[dict]) -> str:
    """Escape raw query IDs when a historical PG example lacks a current short ID."""
    job, tpch = pg
    return (
        rf"\textsuperscript{{a}}Current benchmark query \texttt{{{plot.latex_escape(job['short_query'])}}}: "
        r"SQLStorm \texttt{v1.0/job/queries/13193.sql}-derived, "
        r"\fix{5} relations, right-deep, \texttt{L/F/R/I}, low-selectivity variant.\par" + "\n"
        rf"\textsuperscript{{b}}Current benchmark query \texttt{{{plot.latex_escape(tpch['short_query'])}}}: "
        r"TPC-H Q8-derived, \fix{6} relations, bushy, \texttt{F/R/I/F/L}, low-selectivity variant. "
        r"Both SQL files are byte-identical to their benchmark definitions; this table uses separate "
        r"\fix{1}-thread measurements (TPC-H \fix{SF100}), not the main \fix{32}-thread "
        r"measurements (TPC-H \fix{SF50})."
    )


def runtime_wording(protocols: list[dict]) -> dict[str, str]:
    """Describe recorded samples, never infer a new protocol from script defaults."""
    settings = set()
    for record in protocols:
        count = float(record["timing_samples"])
        if not count.is_integer() or count < 1 or int(count) % 2 == 0:
            raise ValueError("Runtime wording requires a positive odd sample count")
        settings.add((int(count), record["timing_estimator"]))
    if len(settings) != 1:
        raise ValueError("Runtime wording requires one consistent measurement protocol")
    count, estimator = settings.pop()
    expected = "single_post_warmup" if count == 1 else "median_post_warmup"
    if estimator != expected:
        raise ValueError("Runtime sample count and estimator disagree")
    if count == 1:
        return {
            "runtime_time": "single unprofiled post-warmup running time",
            "runtime_times": "single unprofiled post-warmup running times",
            "runtime_method": "Each configuration uses one unprofiled post-warmup timed execution.",
        }
    return {
        "runtime_time": "median of " + plot.number(count, 0) + " unprofiled post-warmup running times",
        "runtime_times": "median unprofiled post-warmup running times over " + plot.number(count, 0)
                         + " executions per configuration",
        "runtime_method": "Each configuration uses " + plot.number(count, 0)
                          + " unprofiled post-warmup timed executions. We report the median of all "
                          "these samples independently for DuckDB and OuterYan, and compute speed-up "
                          "as the ratio of the two medians.",
    }


def fill_fragment(paper: dict, intro_n: int, pg: list[dict], corpus: dict | None = None,
                  policy_rows: list[dict] | None = None) -> str:
    groups = {row["family"]: row for row in paper["runtime"]["outeryan_selected"]}
    total = groups["All"]
    if paper.get("refresh_audit", {}).get("timeout_substituted", 0):
        raise ValueError("Manuscript statistics must exclude all timeout substitutions")
    values = {
        "intro_n": plot.number(intro_n, 0),
        "selected_n": plot.number(total["counts"]["valid"], 0),
        "intro_gm": rf"\fix{{${total['speedup']['geomean']:.2f}\times$}}",
        "intro_max": rf"\fix{{${total['speedup']['max']:.1f}\times$}}",
        "overall_gm": plot.factor(total["speedup"]["geomean"]),
        "overall_max": plot.factor(total["speedup"]["max"]),
        "total_ratio": plot.factor(total["totals"]["speedup"]),
        "runtime_cohort": "valid measured",
        "overall_exclusions": (
            "We report performance statistics only for valid measured queries for which an OuterYan "
            "plan is selected. A query is excluded if either DuckDB or OuterYan times out, "
            "including during warmup or profiling; no timeout limit is substituted for a measured runtime. "
            r"Unexecuted defaults and exact $1\times$ ratios are also excluded."
        ),
    }
    values.update(runtime_wording(paper["method"]["timing_protocols"]))
    corpus = corpus or paper["input_corpus"]
    values["benchmark_n"] = plot.number(corpus["total"], 0)
    values["benchmark_sentence"] = (
        "The final benchmark contains " + plot.number(corpus["total"], 0) +
        " query instances. We report results by workload family, join-tree shape, join-graph topology, "
        "join-type composition, and selectivity level. Performance statistics cover the "
        + plot.number(total["counts"]["valid"], 0)
        + " queries with valid paired runtime measurements and an OuterYan plan selected."
    )
    values["runtime_table"] = runtime_table_tex(
        policy_rows, paper.get("method", {}).get("reporting_minimum_speedup", 0.0)) if policy_rows else ""
    distribution = paper.get("query_distribution", [])
    values["query_distribution"] = (query_distribution_tex(distribution) + "\n" +
                                    query_distribution_discussion_tex(distribution)) if distribution else ""
    audit = paper.get("refresh_audit", {})
    datasets = audit.get("graph_dataset_counts", {})
    values["dataset_note"] = ""
    if datasets.get("epinions"):
        values["dataset_note"] = (
            "The Graph component uses Bitcoin for " + plot.number(datasets.get("bitcoin", 0), 0)
            + " query instances and Epinions for " + plot.number(datasets["epinions"], 0)
            + " instances. The initial replacement cohort contained sixteen queries with previous Bitcoin "
            "runtimes at most " + plot.number(0.1, 1)
            + r"\,s in both configurations. One grouped-count replacement was subsequently retired "
            "at user request after reviewing its predicates. Three additional queries with both "
            "Bitcoin runtimes below " + plot.number(0.2, 1)
            + r"\,s were moved to Epinions for retesting. Predicates are recalibrated to the same "
            "base-input selectivity bands. Old Bitcoin times are not reused. Graph statistics "
            "therefore describe a mixed-dataset workload, not a uniform dataset scaling experiment."
        )
    values["cohort_note"] = ""
    if audit:
        values["cohort_note"] = (
            r"\paragraph{Reporting scope.} The benchmark count describes the full active SQL manifest, "
            "not the performance sample. The introductory speed-up, performance table, runtime figure "
            "and overall analysis use the same " + plot.number(total["counts"]["valid"], 0) +
            r" valid measured OuterYan-selected pairs. We retain sub-second pairs and measured slowdowns, "
            r"but exclude timeouts, failed checks, untimed/default rows, native-plan executions and "
            r"exact $1\times$ ratios. No missing speed-up is replaced with $1\times$."
            + correctness_scope_tex(audit)
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
    values["phase_n"] = plot.number(sum(row["profiles"] for row in paper["phase"]
                                       if plot.normalize_family(row["family"]) != "all"), 0)
    values["phase_analysis"] = phase_discussion_tex(paper["phase"])
    reps = paper["representatives"]
    values["optimization_analysis"] = optimization_discussion_tex(reps)
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
    values["pg_footnotes"] = pg_footnotes_tex(pg)
    template = TEMPLATE.read_text()
    result = re.sub(r"@@([a-z_]+)@@", lambda match: values[match[1]], template)
    if "@@" in result:
        raise ValueError("Unexpanded manuscript placeholder")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="+", help="One new full-run CSV, or prior CSVs plus later partial reruns")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path,
                        help="Override results/plots/YYYYMMDD (latest contributing experiment date)")
    parser.add_argument("--samples-per-family", type=int, default=3)
    parser.add_argument("--phase-samples-per-family", type=int, choices=range(4, 7), default=5,
                        help="Phase-share-diverse figure sample, restricted to speed-up >= 1")
    parser.add_argument("--no-figures", action="store_true", help="Statistics/template validation only")
    parser.add_argument("--replace-tpcds", type=Path,
                        help="Full TPC-DS snapshot: discard older family rows, then apply later partial updates")
    parser.add_argument("--database-renames", type=Path,
                        help="JSON list of explicitly audited path/stat-equivalent database renames")
    parser.add_argument("--minimum-speedup", type=float, default=0.0,
                        help="Deprecated; must be zero. Retain measured slowdowns in the selected cohort")
    parser.add_argument("--case-analysis", type=Path,
                        help="Reviewed LaTeX subsection to replace the Case Query Analysis placeholder")
    parser.add_argument("--duckdb-timeout-substitute", type=int, choices=(0,), default=0,
                        help="Deprecated compatibility option; only 0 is allowed. All timeouts are excluded")
    args = parser.parse_args(argv)
    if args.samples_per_family < 1:
        parser.error("--samples-per-family must be positive")
    if args.minimum_speedup != 0:
        parser.error("--minimum-speedup must be zero: measured slowdowns must not be silently screened")
    if args.replace_tpcds and args.replace_tpcds.resolve() not in [Path(p).resolve() for p in args.csv]:
        parser.error("--replace-tpcds must also be listed as an input CSV")
    case_analysis = args.case_analysis.read_text() if args.case_analysis else None
    rename_evidence = json.loads(args.database_renames.read_text()) if args.database_renames else []
    if not isinstance(rename_evidence, list):
        parser.error("--database-renames must contain a JSON list")
    plot.MIN_RUNTIME_SECONDS = 0.0
    manifest, merged, rejected, pending = current_observations(
        args.csv, args.manifest, args.replace_tpcds, rename_evidence)
    reporting_view = apply_timeout_substitution(merged, args.duckdb_timeout_substitute)
    frame, reporting_excluded = reporting_cohort(reporting_view)
    if frame.empty:
        raise ValueError("No valid measured OuterYan-selected non-unit pairs in the active SQL results")
    source_corpus = benchmark_composition(merged, "Matched source corpus before reporting exclusions")
    manifest_composition = manifest.copy()
    manifest_composition["workload_component"] = manifest_composition.provenance_class.map(PAPER_COMPONENTS)
    if manifest_composition.workload_component.isna().any():
        raise ValueError("Unknown manifest provenance_class; cannot count the complete benchmark")
    corpus = benchmark_composition(manifest_composition, "Full active SQL manifest, independent of execution outcome")
    performance_corpus = benchmark_composition(frame, "Complete non-timeout OuterYan-selected non-unit measured pairs")
    out = output_directory(merged, args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = plot.build_statistics(frame, sources=args.csv)
    report["method"]["population"] = SCREENING
    report["method"]["reporting_minimum_speedup"] = args.minimum_speedup
    report["method"]["reporting_screened_rows"] = 0
    report["method"]["cohort"] = (
        "Only valid measured selected_plan=OUTERYAN pairs with unrounded tm_off/tm_on != 1; "
        "both-subsecond pairs and all measured slowdowns are retained. No fallback/default imputation."
    )
    report["method"]["refresh_scope"] = refresh_scope(merged, len(manifest), len(pending))
    report["method"]["short_query_counts"] = (
        "Legacy JSON counts.both_runtimes_below_1s counts exclusions by the runtime cutoff, "
        "which is disabled here. benchmark_statistics.csv names this excluded_both_subsecond "
        "and separately reports retained_both_subsecond."
    )
    report["method"]["excluded"] = (
        "Exact active-SQL intersection, followed by validity filtering. Historical outcome-based "
        "screening is recorded separately; fallback placeholders, native plans, exact unit ratios and "
        "timeouts are excluded. No new outcome-based speed-up cutoff."
    )
    detail = plot.prepare_queries(frame, "tm")
    measured = detail.valid_timing.to_numpy()
    substituted = plot.timeout_substitution_mask(frame)
    report["method"]["timeout"] = (
        "Exclude the entire query if either DuckDB or OuterYan times out at any stage. "
        "No timeout-limit substitution. Retain original statuses and partial times for diagnostics only."
    )
    # A complete phase profile alone is not enough: require the same valid pair.
    report["phase_profiles"] = plot.build_phase_statistics(frame.loc[measured], "tm")
    paper = plot.build_paper_report(frame, report, args.samples_per_family)
    report["groups"] = [row for row in report["groups"] if row["subset"] == "outeryan_selected"]
    paper["runtime"].pop("all", None)
    for key in ("corpus", "input_corpus"):
        paper[key]["rule"] = COMPOSITION_RULE
    policy_rows = policy_statistics(frame)
    paper["policy_runtime_table"] = policy_rows
    paper["complete_benchmark_composition"] = corpus
    paper["source_benchmark_composition"] = source_corpus
    paper["performance_cohort_composition"] = performance_corpus
    distribution, type_shapes = query_distribution(manifest, frame.loc[measured])
    paper["query_distribution"] = distribution
    paper["query_type_shape_counts"] = type_shapes
    labels = plot.add_short_query_labels(frame.loc[frame.selected_plan.eq("OUTERYAN")])
    pg = pg_cases(manifest, labels)
    native = (merged.selected_plan.eq("DUCKDB") & merged.correct.astype(str).str.upper().eq("TRUE")
              & merged.timing_status.eq("fallback-skip"))
    selected_valid = measured & frame.selected_plan.eq("OUTERYAN").to_numpy()
    selected_untimed = merged.selected_plan.eq("OUTERYAN") & merged.timing_status.eq("fallback-skip")
    diagnostic_detail = plot.prepare_queries(merged, "tm")
    source_timeouts = plot.build_timeout_statistics(diagnostic_detail)
    intro_n = len(frame)
    audit = {
        "manifest": str(args.manifest.resolve()), "manifest_sha256": digest(args.manifest),
        "template_sha256": digest(TEMPLATE), "sources": report["sources"],
        "refresh_script_sha256": digest(Path(__file__)),
        "drawing_script_sha256": digest(Path(plot.__file__)),
        "active_queries": len(manifest), "matched_queries": len(merged), "reported_queries": len(frame),
        "graph_dataset_counts": manifest.loc[manifest.family.eq("graph"), "graph_dataset"].value_counts().to_dict(),
        "graph_dataset_statuses": merged.loc[merged.family.map(plot.normalize_family).eq("Graph")].groupby(["graph_dataset", "timing_status"]).size().rename("queries").reset_index().to_dict("records"),
        "reporting_minimum_speedup": 0.0, "reporting_screened_rows": 0,
        "reporting_excluded_rows": len(reporting_excluded),
        "reporting_exclusions": reporting_excluded.reporting_exclusion.value_counts().to_dict(),
        "pending_queries": len(pending),
        "case_analysis_source": str(args.case_analysis.resolve()) if args.case_analysis else None,
        "case_analysis_sha256": digest(args.case_analysis) if args.case_analysis else None,
        "replace_tpcds_source": str(args.replace_tpcds.resolve()) if args.replace_tpcds else None,
        "database_renames_source": str(args.database_renames.resolve()) if args.database_renames else None,
        "database_renames_sha256": digest(args.database_renames) if args.database_renames else None,
        "database_renames": rename_evidence,
        "rejected_observations": len(rejected), "source_runs": sorted(merged.source_run.unique()),
        "refresh_scope": report["method"]["refresh_scope"],
        "valid_measured_outeryan": int(selected_valid.sum()),
        "timeout_substituted": int(substituted.sum()),
        "duckdb_timeout_substitute_seconds": args.duckdb_timeout_substitute,
        "native_verified_fallback": int(native.sum()),
        "selected_but_untimed": int(selected_untimed.sum()),
        "timeouts": source_timeouts["total"],
        "measured_verified": int((frame.correct.astype(str).str.upper().eq("TRUE") & ~substituted).sum()),
        "measured_correctness_disabled": int((frame.correct.astype(str).str.upper().eq("NOT-CHECKED") & ~substituted).sum()),
        "intro_evaluable_cohort": intro_n,
        "both_subsecond_included": int((measured & frame.tm_off.lt(1) & frame.tm_on.lt(1)).sum()),
        "historical_screening": SCREENING,
        "active_performance_screens": active_performance_screens(args.manifest),
        "intro_definition": "Same complete non-timeout measured selected cohort as table, figures and prose; not the entire manifest",
        "main_runtime_protocol": frame[["timing_threads", "timing_protocol", "timing_samples", "timing_estimator", "warmup_runs_per_side"]].drop_duplicates().to_dict("records"),
        "optimizer_measurement": "optimizer_*_total_s = all_optimizers; not just instrumented OuterYan workflow phases",
    }
    paper["refresh_audit"] = audit
    report["source_diagnostics"] = {"matched_queries": len(merged), "timeouts": source_timeouts,
                                    "reporting_exclusions": audit["reporting_exclusions"]}
    fragment = replace_case_analysis(fill_fragment(paper, intro_n, pg, corpus, policy_rows), case_analysis)
    (out / "paper_updates.tex").write_text(fragment)
    # The main benchmark refresh does not remeasure the separate PG experiment.
    (out / "requested_paper_sections.tex").write_text(
        fragment.split(r"\subsubsection{PostgreSQL Plan Comparison}", 1)[0].rstrip() + "\n")
    (out / "execution_optimization_updates.tex").write_text(execution_optimization_sections(fragment))
    (out / "paper_replacements.tex").write_text(fragment.split(r"\subsubsection{Execution Breakdown}")[0])
    (out / "runtime_by_benchmark.tex").write_text(runtime_table_tex(policy_rows, args.minimum_speedup))
    (out / "query_distribution.tex").write_text(query_distribution_tex(distribution) + "\n" +
                                                query_distribution_discussion_tex(distribution))
    pd.DataFrame(distribution).to_csv(out / "query_distribution.csv", index=False)
    pd.DataFrame(type_shapes).to_csv(out / "query_type_shape_counts.csv", index=False)
    (out / "figure_includes.tex").write_text(figure_includes_tex(
        int(selected_valid.sum()), args.minimum_speedup, int(substituted.sum())))
    write_json(out / "paper_statistics.json", paper)
    write_json(out / "statistics.json", report)
    write_json(out / "refresh_audit.json", audit)
    write_json(out / "pg_query_provenance.json", pg)
    frame.to_csv(out / "current_results.csv", index=False)
    frame.loc[substituted].to_csv(out / "timeout_substitutions.csv", index=False)
    merged.to_csv(out / "merged_current_results.csv", index=False)
    reporting_excluded.to_csv(out / "reporting_excluded.csv", index=False)
    pd.DataFrame(policy_rows).to_csv(out / "policy_benchmark_statistics.csv", index=False)
    write_json(out / "benchmark_composition.json", corpus)
    write_json(out / "source_benchmark_composition.json", source_corpus)
    write_json(out / "performance_cohort_composition.json", performance_corpus)
    manifest_composition.to_csv(
        out / "benchmark_composition_queries.csv", index=False)
    pending.to_csv(out / "pending_queries.csv", index=False)
    rejected.to_csv(out / "excluded_observations.csv", index=False)
    replacement_audit(merged, rejected).to_csv(out / "replaced_observations.csv", index=False)
    labels.to_csv(out / "query_id_map.csv", index=False)
    export_runtime_data(out, manifest, merged, reporting_view, labels)
    merged.loc[selected_untimed].to_csv(out / "selected_but_untimed.csv", index=False)
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
    short_pairs = frame.tm_off.lt(1) & frame.tm_on.lt(1)
    normalized_families = frame.family.map(plot.normalize_family)
    for row in stats:
        row["excluded_both_subsecond"] = row.pop("both_runtimes_below_1s")
        family_rows = True if row["family"] == "all" else normalized_families.eq(row["family"])
        row["retained_both_subsecond"] = int((short_pairs & family_rows).sum())
    pd.DataFrame(stats).to_csv(out / "benchmark_statistics.csv", index=False)
    pd.DataFrame(source_timeouts["distribution"]).to_csv(out / "timeout_summary.csv", index=False)
    pd.DataFrame(source_timeouts["queries"]).to_csv(out / "timeout_queries.csv", index=False)
    reps = paper["representatives"]
    highest = max(reps, key=lambda row: row["outeryan_optimizer_percent"])
    graph = next(row for row in phase_rows if row["family"] == "Graph")
    tpcds = next(row for row in stats if row["subset"] == "outeryan_selected" and row["family"] == "TPC-DS")
    review = f"""REVIEW BEFORE PUBLICATION — manuscript refresh

Population / denominator
Active manifest: {len(manifest)}; matching result rows: {len(merged)}; pending: {len(pending)}.
No additional speed-up cutoff. All valid measured slowdowns remain in the report.
The benchmark sentence counts {corpus['total']} queries in the FULL ACTIVE MANIFEST.
The matched source corpus has {source_corpus['total']} queries; source_benchmark_composition.json preserves its counts.
All original input CSVs remain immutable. merged_current_results.csv has all current SQL matches.
Refresh scope: {audit['refresh_scope']}
current_results.csv is the selected non-unit reporting view; recorded_tm_off/on preserve original values.
merged_current_results.csv retains raw timing values and timeout statuses without substitution.
Graph dataset counts in the active manifest: {json.dumps(audit['graph_dataset_counts'], sort_keys=True)}.
Graph dataset/status counts: {json.dumps(audit['graph_dataset_statuses'], sort_keys=True)}.
Intro, table, prose and runtime figure: {intro_n} valid selected non-unit rows, all complete measured non-timeout pairs. No timeout substitution.
The source diagnostics retain {audit['timeouts']} timeout rows, {int(selected_untimed.sum())} selected-but-untimed
rows and {len(pending)} pending manifest rows. Any timeout on either engine, at any stage, excludes that query from performance statistics and valid selected counts.
Both runtimes <1s: {audit['both_subsecond_included']} retained.
The table has one panel. Its sample and geometric mean equal the headline; all timeout rows are excluded.
Excluded exact 1x means full-precision tm_off/tm_on == 1, not a rounded or approximately-one measurement.
See reporting_excluded.csv for each excluded row and its reason. Native fallback counts are diagnostic only.
Correctness: {audit['measured_verified']} verified; {audit['measured_correctness_disabled']} explicitly unchecked
performance-only pairs. Unchecked performance must not be described as correctness verification.
{SCREENING}
Applied frozen rules: {json.dumps(audit['active_performance_screens'], ensure_ascii=False)}

Manuscript checks and remaining interpretation limits
1. Overall: TPC-DS geometric mean is now {tpcds['geomean']:.4f}x ({tpcds['valid']} valid measured queries).
   'Substantial speedups' describes the aggregate only, not every query or a statistical significance test.
2. Execution discussion now reports Graph R3 = {graph['round3_percent']:.2f}% and Other = {graph['other_percent']:.2f}%,
   distinguishes weighted CPU work from wall time, and removes the stale H-RD-03 causal example.
3. The phase table covers all complete valid selected profiles, not only the figure sample.
4. Runtime description is generated from the recorded sample count and estimator:
   Recorded runtime protocol: {json.dumps(audit['main_runtime_protocol'], sort_keys=True)}
   The separate PG experiment has not been remeasured by this refresh.
5. Optimization now explicitly uses all_optimizers totals per configuration. Workflow phase
   measurements remain separately exported in optimization_workflow_phases.json.
6. Optimization now qualifies the relative cost for short queries: {highest['short_query']} has
   {highest['outeryan_optimizer_ms']:.3f} ms total optimization / {highest['outeryan_s']:.6f} s runtime
   = {highest['outeryan_optimizer_percent']:.2f}%; some representatives are slower than DuckDB.
7. Case Query Analysis: {'reviewed subsection included from ' + str(args.case_analysis) if args.case_analysis else 'supplied TODO retained; no case-analysis source supplied'}.

Fallback recording issue (no harness/optimizer changes made)
{int(selected_untimed.sum())} rows say selected_plan=OUTERYAN but timing_status=fallback-skip.
These rows are NOT established native-plan fallbacks and are NOT measured speed-ups.
See selected_but_untimed.csv. Their trace flags are preserved rather than relabeled.

Figures and representative selection
All reporting-cohort rows are plotted, including sub-second pairs and slowdowns. No timeout query is plotted.
Phase figure uses up to {args.phase_samples_per_family} queries per family with speed-up >= 1,
selected by farthest-point sampling of normalized CPU shares, starting nearest the family centroid.
Optimization table uses up to {args.samples_per_family} queries per family:
shape quotas, then evenly spaced DuckDB-runtime ranks, without speed-up ranking.
Phase-summary table uses ALL valid complete selected profiles, not only the figure's sample.
Percentages are sum(phase CPU seconds) / sum(total CPU seconds); CPU seconds are not wall time.
Full-precision times drive all ratios; displayed numbers are rounded only at formatting.
Footnotes map both PG examples to byte-identical current SQL and original source paths in
pg_query_provenance.json. PG measurements remain separate (cpu8, 1 thread, TPC-H SF100).

Refresh after new results arrive
For a new complete benchmark run, pass only its CSV; do not carry earlier measurements forward.
For a partial rerun, pass the prior source CSV(s) plus the new partial CSV. Latest exact-SQL status
wins, including failure/timeout; incompatible per-family environments are rejected. Use
--replace-tpcds only for an explicit complete TPC-DS replacement snapshot, not a full multi-family run.
The default output is results/plots/YYYYMMDD for the latest contributing experiment date. If another
snapshot already uses that date, specify --output-dir results/plots/YYYYMMDD for the refresh date
to preserve the earlier snapshot. Figures, statistics and LaTeX share that directory.
Source hashes are in refresh_audit.json.
"""
    (out / "REVIEW.txt").write_text(review)
    (out / "ANALYSIS.txt").write_text(review)
    write_json(out / "runtime_merge_audit.json", audit)
    command = ["python3", str(Path(__file__).resolve()), *[str(Path(path).resolve()) for path in args.csv],
               "--manifest", str(args.manifest.resolve()), "--output-dir", str(out),
               "--samples-per-family", str(args.samples_per_family),
               "--phase-samples-per-family", str(args.phase_samples_per_family),
               "--minimum-speedup", str(args.minimum_speedup),
               "--duckdb-timeout-substitute", str(args.duckdb_timeout_substitute)]
    if args.replace_tpcds:
        command += ["--replace-tpcds", str(args.replace_tpcds.resolve())]
    if args.database_renames:
        command += ["--database-renames", str(args.database_renames.resolve())]
    if args.case_analysis:
        command += ["--case-analysis", str(args.case_analysis.resolve())]
    # Attribute counts read catalog schemas only. Keep their explicit local
    # paths in the reproduction command after scale-qualified DB renaming.
    schema_variables = {"Graph": "GRAPH_DB", "TPC-H": "TPCH_DB",
                        "TPC-DS": "TPCDS_DB", "JOB": "JOB_DB"}
    schemas = {schema_variables[row["family"]]: row["attribute_database"] for row in reps}
    command = ["env", *[key + "=" + value for key, value in sorted(schemas.items())], *command]
    (out / "REPRODUCE.txt").write_text(
        "Regenerate this snapshot (statistics, LaTeX and both figures):\n\n"
        + shlex.join(command) + "\n\n"
        "For a new complete benchmark run, pass only the new CSV. For a partial rerun, append "
        "its CSV after the prior source CSV argument(s); the latest matching SQL status, including "
        "failure, replaces the old observation. Use --replace-tpcds only for a complete TPC-DS-only "
        "replacement snapshot. The default output date is the latest contributing experiment date; "
        "use --output-dir results/plots/YYYYMMDD with the refresh date to preserve an earlier "
        "same-date snapshot. Do not reuse a case-analysis fragment without rechecking its numbers.\n"
    )
    if not args.no_figures:
        plot._load_plotting()
        plot.write_standalone_runtime_figures(out, frame, "active_manifest_refresh", "tm",
                                             sample_per_family=args.samples_per_family,
                                             phase_sample_per_family=args.phase_samples_per_family)
    print(json.dumps(audit, indent=2))
    print(f"Paper fragment and figures: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
