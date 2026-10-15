#!/usr/bin/env python3
"""Materialize the approved 20-replacement measurement snapshot, without SQL runs.

This tool only replays the two hash-pinned historical inputs. It is not a
selector for future results: a new full run must be reported on its own.
"""
import argparse
import csv
import json
from pathlib import Path

import gen_experiment_result as plot
import refresh_paper_results as refresh
import tpch_tuning_promotion as promotion

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "auto_test/results/plots/20261013"


def prepare_snapshot(out):
    spec = promotion.policy()
    inputs = promotion.measurement_snapshot()
    sources = {key: ROOT / inputs[key + "_csv"] for key in ("baseline", "replacement")}
    for key, path in sources.items():
        if promotion.b.digest(path) != inputs[key + "_sha256"]:
            raise ValueError("Pinned measurement source changed: " + str(path))
    active = promotion.b.ROOT / "benchmark"
    promotion.validate(active, promotion.b.validate(active))
    promoted = {r["query_id"]: r for r in promotion.replacements()}
    with sources["replacement"].open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = [r for r in reader if r["query"] in promoted]
    if len(rows) != 20 or len({r["query"] for r in rows}) != 20:
        raise ValueError("Expected exactly 20 replacement observations")
    for row in rows:
        if row["sql_content_sha256"] != promoted[row["query"]]["content_sha256"]:
            raise ValueError("Replacement observation SQL hash mismatch")
    out.mkdir(parents=True, exist_ok=True)
    subset = out / "frozen_20_input.csv"
    # Copy original CSV fields as strings: no recomputation or rounded runtimes.
    promotion.b.write_csv(subset, rows, fields)
    plot.MIN_RUNTIME_SECONDS = 0.0
    manifest, merged, rejected, pending = refresh.current_observations(
        [str(sources["baseline"]), str(subset)], active / "manifest.csv")
    if len(merged) != 720 or not pending.empty:
        raise ValueError("Incomplete frozen snapshot")
    is_new = merged["query"].isin(promoted)
    if is_new.sum() != 20 or not merged.loc[is_new, "source_csv"].eq(str(subset.resolve())).all():
        raise ValueError("Wrong replacement source")
    if not merged.loc[~is_new, "source_csv"].eq(str(sources["baseline"].resolve())).all():
        raise ValueError("An unchanged query picked up a newer observation")
    merged["original_source_csv"] = str(sources["baseline"])
    merged.loc[is_new, "original_source_csv"] = str(sources["replacement"])
    selected, excluded = refresh.reporting_cohort(merged)
    if len(selected) != 281 or selected.family.eq("TPC-H").sum() != 80:
        raise ValueError("Pinned snapshot cohort changed")
    return sources, manifest, merged, selected, excluded, rejected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    out = args.output_dir.resolve()
    sources, manifest, merged, selected, excluded, rejected = prepare_snapshot(out)
    stats = refresh.policy_statistics(selected)
    for row in stats:
        row.pop("mean", None)
        group = selected if row["family"] == "All" else selected.loc[
            selected.family.map(plot.normalize_family).eq(row["family"])]
        ratios = group.tm_off / group.tm_on
        row.update(faster=int(ratios.gt(1).sum()), slower=int(ratios.lt(1).sum()))
        row["family"] = plot.figure_family_label(row["family"])
    phase = plot.build_phase_statistics(selected, "tm")
    phase_rows = []
    for row in phase["groups"]:
        if row["scope"] not in ("overall", "benchmark"):
            continue
        phase_rows.append(dict(
            family="All" if row["scope"] == "overall" else plot.figure_family_label(row["family"]),
            n=row["profiles"], operator_total_s=row["cpu_total_s"],
            **{k + "_percent": 100 * v for k, v in row["cpu_weighted_fraction"].items()},
            **{k + "_s": v for k, v in row["component_seconds"].items()}))
    frames = {"merged_results": merged, "selected_results": selected,
              "reporting_excluded": excluded, "superseded_observations": rejected,
              "benchmark_statistics": plot.pd.DataFrame(stats),
              "phase_summary": plot.pd.DataFrame(phase_rows)}
    for name, frame in frames.items():
        frame.to_csv(out / ("frozen_20_" + name + ".csv"), index=False)
    audit = dict(
        policy=str(promotion.POLICY), policy_sha256=promotion.b.digest(promotion.POLICY),
        manifest_sha256=promotion.b.digest(refresh.DEFAULT_MANIFEST),
        selection_disclosure=promotion.policy()["selection_disclosure"],
        source_files={key: dict(path=str(path), sha256=promotion.b.digest(path))
                      for key, path in sources.items()},
        rows_from_old_run=700, rows_from_new_run=20, workload_queries=len(manifest),
        valid_selected_queries=len(selected), tpch_valid_selected_queries=80,
        statistics=stats, exclusions=excluded.reporting_exclusion.value_counts().to_dict(),
        no_new_query_execution=True,
        timeout_policy="Exclude any timeout on either engine; no timeout-limit imputation.",
        future_results="Use each new full run in its entirety; never enforce these historical statistics.")
    (out / "frozen_20_audit.json").write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    overall = next(row for row in stats if row["family"] == "All")
    tpch = next(row for row in stats if row["family"] == "TPC-H")
    text = (
        "Frozen 20-query TPC-H setting, approved 2026-10-13\n\n"
        "14 predicate-only replacements + Q5 bushy low/medium/high + Q5 right-deep low/medium/high.\n"
        "720 workload instances; 281 complete measured OuterYan-selected pairs, including 80 TPC-H.\n"
        "700 observations from CPU9 20261010_150834; only 20 changed SQLs use CPU9 20261013_000640.\n"
        "This is a post-hoc selected composite, NOT a new complete-run experiment.\n"
        + promotion.policy()["selection_disclosure"] + "\n\n"
        + plot.pd.DataFrame(stats)[["family", "n", "geomean", "median", "max", "total_ratio", "faster", "slower"]].to_string(index=False, float_format=lambda x: f"{x:.9f}")
        + f"\n\nOverall geomean = {overall['geomean']:.12f}x. TPC-H = {tpch['geomean']:.12f}x.\n"
        "TPC-H faster: 63/80 (78.75%); slower: 17/80 (21.25%).\n"
        "Median of five post-warmup executions, 32 threads, SF50, 600s per execution per engine.\n"
        "Either-side timeouts and unmeasured fallback defaults excluded; measured slowdowns and short pairs retained.\n"
        "Raw input CSVs are unchanged. This setting does not guarantee the same result on a future run.\n"
        "Run auto_test/refresh_fixed_tpch_paper.py to refresh the normal figure/statistics filenames and manuscript.\n"
    )
    (out / "FROZEN_TPCH_SETTING.txt").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
