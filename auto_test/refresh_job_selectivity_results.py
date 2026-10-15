"""Replace one JOB observation in the approved snapshot; never retime or select runs."""
import argparse
import csv
from pathlib import Path

import balanced_benchmark as b
import gen_experiment_result as plot
import job_selectivity_update as update
import refresh_paper_results as refresh
import tpch_tuning_promotion as tpch

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / "auto_test/results/plots/20261013"
DEFAULT_OUT = ROOT / "auto_test/results/plots/20261014"


def normalized_input(out):
    """Only remap the pilot name; SQL hashes and every measured value stay intact."""
    spec = update.policy()
    source = ROOT / spec["measurement_csv"]
    if b.digest(source) != spec["measurement_sha256"]:
        raise ValueError("JOB pilot measurements changed")
    with source.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        matches = [r for r in reader if r["query"] == spec["measurement_query"]]
    if len(matches) != 1:
        raise ValueError("Expected exactly one measured JOB candidate")
    row = matches[0]
    if (row["sql_content_sha256"] != spec["content_sha256"] or
            row["selected_plan"] != "OUTERYAN" or row["timing_status"] != "measured" or
            row["duckdb_status"] != "measured" or row["outeryan_status"] != "measured" or
            row["timing_samples"] != "5" or row["timing_threads"] != "32" or
            row["duckdb_timeout_seconds"] != "600" or row["outeryan_timeout_seconds"] != "600"):
        raise ValueError("JOB candidate identity or measurement protocol mismatch")
    row["measurement_query"] = row["query"]
    row["measurement_sql_path"] = row["sql_path"]
    row["measurement_source_csv"] = str(source)
    row["query"] = spec["original"]["query_id"]
    row["sql_path"] = spec["original"]["path"]
    output = out / "job_update_input_20261014_112803_t32.csv"
    b.write_csv(output, [row], fields + ["measurement_query", "measurement_sql_path", "measurement_source_csv"])
    return output


def statistics(frame, labels):
    records = refresh.policy_statistics(frame)
    for row in records:
        group = frame if row["family"] == "All" else frame.loc[
            frame.family.map(plot.normalize_family).eq(row["family"])]
        ratios = group.tm_off / group.tm_on
        minimum = group.loc[ratios.idxmin()]
        row.pop("mean", None)
        row.update(min_query=minimum["query"], min_short_query=labels[minimum["query"]],
                   min_duckdb_s=float(minimum.tm_off), min_outeryan_s=float(minimum.tm_on),
                   below_07=int(ratios.lt(.7).sum()), below_1=int(ratios.lt(1).sum()),
                   faster=int(ratios.gt(1).sum()))
        row["family"] = plot.figure_family_label(row["family"])
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    active = b.ROOT / "benchmark"
    update.validate(active, b.validate(active))
    if not (active / update.MARKER).exists():
        raise ValueError("Promote the approved JOB SQL before updating its statistics")
    plot.MIN_RUNTIME_SECONDS = 0.0
    baseline = tpch.measurement_snapshot()
    original = ROOT / baseline["baseline_csv"]
    if b.digest(original) != baseline["baseline_sha256"]:
        raise ValueError("Baseline measurements changed")
    # Use the prior approved 20 rows, not the entire TPC-H pilot or its controls.
    tpch_input = PRIOR / "frozen_20_input.csv"
    tpch_source = ROOT / baseline["replacement_csv"]
    if b.digest(tpch_source) != baseline["replacement_sha256"]:
        raise ValueError("TPC-H source measurements changed")
    with tpch_source.open(newline="") as handle:
        measured_tpch = {r["query"]: r for r in csv.DictReader(handle)}
    actual_tpch = b.read_manifest(tpch_input)
    if {r["query"] for r in actual_tpch} != {r["query_id"] for r in tpch.replacements()} or any(
            r != measured_tpch[r["query"]] for r in actual_tpch):
        raise ValueError("Frozen TPC-H input changed")
    job_input = normalized_input(out)
    manifest, merged, rejected, pending = refresh.current_observations(
        [str(original), str(tpch_input), str(job_input)], active / "manifest.csv")
    selected, excluded = refresh.reporting_cohort(merged)
    if len(manifest) != 720 or len(merged) != 720 or not pending.empty or len(selected) != 281:
        raise ValueError("Unexpected benchmark or reporting membership")
    prior = plot.pd.read_csv(PRIOR / "current_results.csv")
    old = prior.set_index("query").sort_index()
    new = selected.set_index("query").sort_index()
    query = update.policy()["original"]["query_id"]
    if set(old.index) != set(new.index):
        raise ValueError("Performance cohort changed")
    preserved = old.index.difference([query])
    for column in ("tm_off", "tm_on", "sql_content_sha256", "selected_plan", "timing_status", "source_run"):
        if not old.loc[preserved, column].equals(new.loc[preserved, column]):
            raise ValueError("An unrelated measurement changed: " + column)
    labels = plot.pd.read_csv(PRIOR / "query_id_map.csv").set_index("query").short_query.to_dict()
    before, after = statistics(prior, labels), statistics(selected, labels)
    merged = refresh.apply_timeout_substitution(merged)
    selected = refresh.apply_timeout_substitution(selected)
    selected["short_query"] = selected["query"].map(labels)
    selected["tm_speedup"] = selected.tm_off / selected.tm_on
    ranked = selected.sort_values("tm_speedup")
    for name, frame in (("merged_results", merged), ("selected_results", selected),
                        ("reporting_excluded", excluded), ("superseded_observations", rejected),
                        ("benchmark_statistics", plot.pd.DataFrame(after)),
                        ("slow_queries", ranked.loc[ranked.tm_speedup.lt(1), [
                            "short_query", "family", "query", "tm_off", "tm_on", "tm_speedup"]])):
        frame.to_csv(out / ("job_update_" + name + ".csv"), index=False)
    audit = dict(
        policy=str(update.POLICY), policy_sha256=b.digest(update.POLICY),
        manifest_sha256=b.digest(active / "manifest.csv"),
        source_measurement=str(ROOT / update.policy()["measurement_csv"]),
        source_sha256=update.policy()["measurement_sha256"],
        source_query=update.policy()["measurement_query"], active_query=query,
        prior_snapshot=str(PRIOR), replaced_observations=1, other_selected_observations_unchanged=280,
        tpch_sql_and_measurements_unchanged=True, benchmark_queries=720, valid_selected=281,
        before=before, after=after, no_new_execution=True,
        description="Composite snapshot: change only the approved JOB query and its measured pair. Raw files are unchanged.",
        reporting_rule="Exclude either-side timeouts, unmeasured fallbacks and exact unit ratios; retain subsecond measured pairs.")
    b.write_json(out / "job_update_audit.json", audit)
    print(plot.pd.DataFrame(after)[["family", "n", "geomean", "median", "min", "min_short_query", "max", "below_07", "below_1"]].to_string(index=False))
    print("JOB-only result update: " + str(out))


if __name__ == "__main__":
    main()
