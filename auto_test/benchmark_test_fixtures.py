"""Frozen inputs for historical pilot tests, independent of the active cohort.

Reconstruct earlier stages from checked-in SQL and policy validators, never
from measured results. Production guards still reject changed active inputs.
"""
import csv
import shutil
from pathlib import Path
import tempfile

import balanced_benchmark as benchmark
import benchmark_plan_cohort as cohort
import job_selectivity_update
import tpch_selectivity_update
import tpch_tuning_promotion


def historical_corpus(owner, stage="pre_cohort"):
    source = cohort.input_corpus()
    if stage == "pre_cohort":
        return source
    if stage not in {"before_tpch_selectivity", "before_job", "before_tuning"}:
        raise ValueError("Unknown historical test stage: " + stage)
    temporary = tempfile.TemporaryDirectory(prefix="outeryan-historical-test-")
    cleanup = getattr(owner, "addClassCleanup", None) if isinstance(owner, type) else owner.addCleanup
    cleanup(temporary.cleanup)
    output = Path(temporary.name) / "benchmark"
    shutil.copytree(source, output)
    rows = benchmark.read_manifest(output / "manifest.csv")
    fields = list(rows[0])
    validators = [tpch_selectivity_update]
    if stage in {"before_job", "before_tuning"}:
        validators.append(job_selectivity_update)
    for validator in validators:
        rows, paths = validator.validate(output, rows)
        for relative, archived in paths.items():
            shutil.copyfile(archived, output / relative)
        (output / validator.MARKER).unlink()
    with (output / "manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    if stage == "before_tuning":
        _, paths, _ = tpch_tuning_promotion.validate(output, rows)
        for relative, archived in paths.items():
            shutil.copyfile(archived, output / relative)
        shutil.copyfile(tpch_tuning_promotion.ARCHIVE / "prior_manifest.csv", output / "manifest.csv")
        (output / tpch_tuning_promotion.MARKER).unlink()
    # Fail if a historical fixture silently resolves a newer SQL definition.
    for row in benchmark.read_manifest(output / "manifest.csv"):
        if benchmark.digest(output / row["path"]) != row["content_sha256"]:
            raise ValueError("Historical fixture SQL mismatch: " + row["query_id"])
    return output
