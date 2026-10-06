#!/usr/bin/env python3
"""Export a labelled, post-hoc review subset without changing the benchmark.

The original CSV, SQL, paper tables and standard plots are never overwritten.
Run with --help for the explicit runtime and speed-up selection policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import gen_experiment_result as results

pd = results.pd
np = results.np
FAMILIES = ("all", "Graph", "TPC-H", "TPC-DS", "JOB")


def classify(frame, minimum_runtime=1.0, minimum_speedup=0.8):
    """Keep both timings >= the threshold; compare the unrounded ratio."""
    if minimum_runtime <= 0 or minimum_speedup <= 0:
        raise ValueError("Thresholds must be positive")
    detail = results.prepare_queries(frame, "tm")
    # The standard report's threshold is intentionally not changed by this tool.
    complete = detail.exclusion_reason.isin(("", "both_runtimes_below_1s"))
    detail["speedup"] = (detail.off_s / detail.on_s).where(complete)
    long_enough = complete & detail.off_s.ge(minimum_runtime) & detail.on_s.ge(minimum_runtime)
    selected = long_enough & detail.speedup.ge(minimum_speedup)
    stages = {
        "complete_measured_pairs": complete,
        "previous_report_either_runtime_ge_1s": detail.valid_timing.copy(),
        "both_runtimes_ge_threshold": long_enough,
        "review_speedup_filtered": selected,
        "sensitivity_duckdb_runtime_only": complete & detail.off_s.ge(minimum_runtime)
        & detail.speedup.ge(minimum_speedup),
    }
    reasons = detail.exclusion_reason.copy()
    reasons.loc[complete & ~long_enough] = "either_runtime_below_threshold"
    reasons.loc[long_enough & ~selected] = "speedup_below_threshold"
    reasons.loc[selected] = "retained"
    detail["review_status"] = reasons
    return detail, stages


def statistics(detail, stages):
    summaries, bins, strata = [], [], []
    for stage, mask in stages.items():
        for family in FAMILIES:
            subset = detail.loc[mask & (detail.family.eq(family) if family != "all" else True)]
            row = {"stage": stage, "family": family, "n": len(subset),
                   "faster": int(subset.speedup.gt(1).sum()),
                   "slower": int(subset.speedup.lt(1).sum())}
            for metric in ("speedup", "off_s", "on_s"):
                row.update({f"{metric}_{key}": value
                            for key, value in results.distribution(subset[metric]).items()})
            row["sum_duckdb_s"] = float(subset.off_s.sum())
            row["sum_outeryan_s"] = float(subset.on_s.sum())
            row["ratio_of_time_sums"] = row["sum_duckdb_s"] / row["sum_outeryan_s"] if len(subset) else None
            summaries.append(row)
            for metric, boundaries, labels in (
                ("off_s", [0, 1, 2, 5, 10, 30, 60, 600, np.inf],
                 ["<1s", "1–2s", "2–5s", "5–10s", "10–30s", "30–60s", "60–600s", ">=600s"]),
                ("on_s", [0, 1, 2, 5, 10, 30, 60, 600, np.inf],
                 ["<1s", "1–2s", "2–5s", "5–10s", "10–30s", "30–60s", "60–600s", ">=600s"]),
                ("speedup", [0, .8, 1, 2, 5, 10, np.inf],
                 ["<0.8x", "0.8–1x", "1–2x", "2–5x", "5–10x", ">=10x"]),
            ):
                counts = pd.cut(subset[metric], boundaries, labels=labels, right=False).value_counts(sort=False)
                for label, count in counts.items():
                    bins.append({"stage": stage, "family": family, "metric": metric,
                                 "interval_left_closed": label, "n": int(count),
                                 "fraction": int(count) / len(subset) if len(subset) else None})
        for dimension in ("family", "workload_category", "tree_shape", "join_graph_topology",
                          "selectivity_level", "relation_count", "join_type_composition"):
            for value, count in detail.loc[mask, dimension].fillna("unknown").value_counts().items():
                strata.append({"stage": stage, "dimension": dimension, "value": value, "n": int(count)})
    return pd.DataFrame(summaries), pd.DataFrame(bins), pd.DataFrame(strata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--minimum-runtime", type=float, default=1.0,
                        help="Both DuckDB and OuterYan must meet this minimum in seconds")
    parser.add_argument("--minimum-speedup", type=float, default=0.8)
    args = parser.parse_args()
    if args.output_dir.resolve() == args.input.resolve().parent:
        parser.error("Use a separate review output directory")
    frame = results.load([str(args.input)]).reset_index(drop=True)
    detail, stages = classify(frame, args.minimum_runtime, args.minimum_speedup)
    summary, bins, strata = statistics(detail, stages)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "query_selection.csv", index=False)
    selected = stages["review_speedup_filtered"]
    frame.loc[selected].to_csv(output / "retained_results.csv", index=False)
    detail.loc[~selected].to_csv(output / "excluded_queries.csv", index=False)
    summary.to_csv(output / "statistics_by_stage.csv", index=False)
    bins.to_csv(output / "runtime_and_speedup_distribution.csv", index=False)
    strata.to_csv(output / "workload_distribution.csv", index=False)
    counts = pd.crosstab(detail.family, detail.review_status).reindex(FAMILIES[1:], fill_value=0)
    counts.to_csv(output / "selection_counts.csv")
    (output / "retained_query_paths.txt").write_text(
        "".join(f"{path}\n" for path in detail.loc[selected, "sql_path"]), encoding="utf-8")

    # Join source metadata to the exact identities, preserving the measured revision.
    manifest_path = Path(__file__).resolve().parent / "outerjoin_benchmark/benchmark/manifest.csv"
    manifest = pd.read_csv(manifest_path)
    if not frame.corpus_revision.isin(manifest.corpus_revision.unique()).all():
        raise ValueError("Current manifest does not match the experiment revision")
    metadata = manifest[["query_id", "source_query", "source_location", "selectivity_profile",
                         "calibration_fraction", "semantic_tier"]]
    enriched = frame.merge(metadata, left_on="query", right_on="query_id", validate="one_to_one", how="left")
    if enriched.query_id.isna().any():
        raise ValueError("Missing manifest identity")
    enriched["unrounded_speedup"] = detail.speedup
    enriched["review_status"] = detail.review_status
    enriched["semijoin_cpu_percent"] = 100 * (
        enriched.profile_round1_operator_s + enriched.profile_round2_operator_s) / enriched.profile_cpu_time_s
    enriched["round1_cpu_percent"] = 100 * enriched.profile_round1_operator_s / enriched.profile_cpu_time_s
    enriched["undiscounted_cost_ratio"] = (
        enriched.candidate_join_cost + enriched.semijoin_raw_cost) / enriched.baseline_cost
    tpcds = enriched.loc[detail.family.eq("TPC-DS")]
    tpcds.to_csv(output / "tpcds_diagnostic_rows.csv", index=False)
    high = enriched.loc[enriched.semantic_tier.eq("high")].copy()
    high["exceeds_proposed_60pct_cap"] = high.calibration_fraction.gt(.6)
    high.to_csv(output / "high_selectivity_audit.csv", index=False)
    timeout = detail.exclusion_reason.eq("timeout")
    timeout_rows = []
    for dimension in ("family", "selectivity_level", "tree_shape", "relation_count"):
        for value, indices in detail.groupby(dimension, dropna=False).groups.items():
            n_timeout = int(timeout.loc[indices].sum())
            timeout_rows.append({"dimension": dimension, "value": value, "total": len(indices),
                                 "timeout": n_timeout, "timeout_fraction": n_timeout / len(indices)})
    pd.DataFrame(timeout_rows).to_csv(output / "original_timeout_distribution.csv", index=False)

    policy = {
        "input": str(args.input.resolve()),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "minimum_runtime_seconds_each_engine": args.minimum_runtime,
        "minimum_speedup_unrounded_duckdb_div_outeryan": args.minimum_speedup,
        "timeout_seconds_per_statement": results.TIMEOUT_SECONDS,
        "scope": "POST-HOC REVIEW SUBSET, not unbiased overall benchmark performance",
        "fallback_policy": "unexecuted fallback-skip rows excluded, never treated as measured 1x",
        "timing_summary": "sum of per-query median execution times, NOT total experiment wall time",
        "changes": "No SQL, generator, optimizer, original result or standard paper report changed",
        "stage_counts": {name: int(mask.sum()) for name, mask in stages.items()},
        "exclusive_reasons": {str(k): int(v) for k, v in detail.review_status.value_counts().items()},
    }
    (output / "selection_policy.json").write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    final = summary.loc[summary.stage.eq("review_speedup_filtered")]
    lines = ["# 筛选后 review 子集统计", "",
             "注意：按实测 speed-up 删除慢例是事后筛选。本表不代表原始完整 benchmark 的性能；"
             "论文整体结论仍应报告完整集合和失败/超时覆盖。原始 SQL、CSV 和论文表格均保留。", "",
             f"条件：正确、完成、非 fallback；DuckDB 和 OuterYan **各自 ≥{args.minimum_runtime:g}s**；"
             f"未舍入 DuckDB/OuterYan ≥{args.minimum_speedup:g}。超时沿用每语句 600s，不填补为 600s。", "",
             "两侧均要求 ≥1s 会同时排除 DuckDB 较慢但 OuterYan <1s 的大幅加速样本；"
             "statistics_by_stage.csv 额外提供仅按 DuckDB ≥阈值的敏感性结果。", "",
             "| Family | N | Geomean | Median | Min | Max | Sample SD | DuckDB total (s) | OuterYan total (s) |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for _, row in final.iterrows():
        lines.append(f"| {row.family} | {row.n} | {row.speedup_geomean:.3f} | {row.speedup_median:.3f} | "
                     f"{row.speedup_min:.3f} | {row.speedup_max:.3f} | {row.speedup_stddev:.3f} | "
                     f"{row.sum_duckdb_s:.3f} | {row.sum_outeryan_s:.3f} |")
    lines += ["", "## 逐步筛选", "", "| Stage | N |", "|---|---:|"]
    lines += [f"| {name} | {int(mask.sum())} |" for name, mask in stages.items()]
    lines += ["", "## 时间分布", "", "区间左闭右开；各查询使用三次运行的中位数。", "",
              "| Interval | DuckDB | OuterYan |", "|---|---:|---:|"]
    selected_bins = bins.loc[bins.stage.eq("review_speedup_filtered") & bins.family.eq("all")]
    for label in selected_bins.loc[selected_bins.metric.eq("off_s"), "interval_left_closed"]:
        b = selected_bins.loc[selected_bins.interval_left_closed.eq(label)].set_index("metric")
        lines.append(f"| {label} | {b.loc['off_s', 'n']} | {b.loc['on_s', 'n']} |")
    lines += ["", "## 输出", "",
              "- statistics_by_stage.csv：每阶段/benchmark 的几何均值、median、min/max、样本标准差、分位数、时间和。",
              "- query_selection.csv / excluded_queries.csv：逐 query 分类、排除原因和实际时间。",
              "- retained_results.csv / retained_query_paths.txt：保留子集，不替换默认 benchmark。",
              "- runtime_and_speedup_distribution.csv / workload_distribution.csv：时间、speed-up、shape/selectivity 等分布。",
              "- tpcds_diagnostic_rows.csv：全部 TPC-DS，包括失败、fallback、成本和分轮 CPU 数据。",
              "- high_selectivity_audit.csv：原有高档校准值及 >60% 标记；尚未改变任何谓词。",
              "- original_timeout_distribution.csv：原始集合的超时分布，不因筛选而消失。",
              "- selection_policy.json：输入校验值、边界、统计口径。", ""]
    (output / "STATISTICS.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(policy["stage_counts"], indent=2))
    print(f"Review outputs: {output.resolve()}")


if __name__ == "__main__":
    main()
