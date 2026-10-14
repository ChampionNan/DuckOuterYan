"""Redraw only the representative phase figure from a labeled result snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import gen_experiment_result as plot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True,
                        help="Selected measured snapshot with stable short_query labels")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--per-family", type=int, default=4)
    parser.add_argument("--max-other-share", type=float, default=.5)
    args = parser.parse_args(argv)
    frame = plot.pd.read_csv(args.csv)
    if "short_query" not in frame or frame.short_query.isna().any() or frame.short_query.duplicated().any():
        raise ValueError("Input must contain unique, complete short_query labels")
    plot.MIN_RUNTIME_SECONDS = 0
    samples = plot.diverse_phase_samples(frame, args.per_family, args.max_other_share)
    if samples.empty:
        raise ValueError("No eligible complete measured OuterYan profiles")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    save = plot.save_page

    def operator_labels(pdf, figure):
        for axis in figure.axes:
            if axis.get_xlabel() == "CPU Time (%)":
                axis.set_xlabel("Operator time (%)")
        save(pdf, figure)

    with patch.object(plot, "save_page", operator_labels), \
         patch.object(plot, "PROFILE_CPU_TOTAL_LABEL", "Total operator time"):
        plot.write_figure_pair(
            args.output_dir, "phase_breakdown_outeryan",
            lambda pdf: plot.page_phase(pdf, samples, "current", preselected=True))

    columns = [c for c in (
        "query", "short_query", "family", "topology", "source_run", "source_csv",
        "sql_content_sha256", "selected_plan", "tm_off", "tm_on", "profile_threads",
        "profile_total_time_s", "profile_wall_time_s", "_phase_sum_error_s",
        "_family_available", "_family_speedups", "_phase_other_limit_relaxed",
    ) if c in samples]
    columns += [c for _, seconds, ratio, _ in plot.PHASES for c in (seconds, ratio)]
    data = samples[columns].copy()
    data["speedup"] = data.tm_off / data.tm_on
    data.to_csv(args.output_dir / "phase_representative_queries.csv", index=False)
    audit = dict(
        source_csv=str(args.csv.resolve()),
        source_sha256=hashlib.sha256(args.csv.read_bytes()).hexdigest(),
        source_rows=len(frame), per_family=args.per_family, max_other_share=args.max_other_share,
        selection="Measured OuterYan speed-up >= 1; prefer Other OP within the limit. "
                  "If insufficient, take the lowest-Other OP queries needed for the quota. "
                  "Then select diverse phase compositions; no ranking by speed-up magnitude.",
        figure_only=True, benchmark_and_population_statistics_unchanged=True,
        queries=json.loads(data.to_json(orient="records", double_precision=15)),
    )
    (args.output_dir / "phase_queries.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(data[["family", "short_query", "profile_other_ratio", "speedup"]].to_string(index=False))


if __name__ == "__main__":
    main()
