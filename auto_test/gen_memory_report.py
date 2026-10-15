#!/usr/bin/env python3
"""Audit raw memory profiles and render comparisons without changing measurements.

The query root includes observations not necessarily present in its child tree.
Keep the original strict-validator status, but validate total metrics separately.
Phase observations are shared buffer-pool footprints, not owned allocations.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

from memory_profile import MEMORY, SPILL, PHASES, normalize, phase

FAMILIES = {"graph": "SGPB", "tpch": "TPC-H", "tpcds": "TPC-DS", "job": "JOB"}
COLORS = {"graph": "#7A7A7A", "tpch": "#E64B35", "tpcds": "#315EFB", "job": "#00A087"}
MIB = 2 ** 20
ENGINE_COLORS = ("#A78BFA", "#FB7185")
EXPECTED_WARNING = "Operator memory peaks missing/stale; rebuild with memory profiling patch"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def walk(node):
    for child in node.get("children", []):
        yield child
        yield from walk(child)


def audit_side(run, index, engine, side, sql):
    assert side["exit_code"] == 0 and side["stage"] == "done", (index, engine)
    assert side["warmups_completed"] == side["measured_executions_completed"] == 1
    assert side["timeout_seconds"] == 600
    assert side["status"] in ("ok", "profile_error")
    if side["status"] == "profile_error":
        assert side["error"] == EXPECTED_WARNING
    prefix = run / "profiles" / f"{index:03d}_{engine}"
    path = prefix.with_suffix(".profile.json")
    raw = json.loads(path.read_text())
    assert normalize(raw["query_name"]) == normalize(sql), path
    nodes = list(walk(raw))
    assert nodes
    for key in (MEMORY, SPILL, "latency"):
        assert math.isfinite(raw[key]) and raw[key] >= 0, (path, key)
    for node in nodes:
        for key in (MEMORY, SPILL):
            assert 0 <= node[key] <= raw[key], (path, key)
    child_max = max(n[MEMORY] for n in nodes)
    assert child_max > 0  # Reject an unpatched, all-zero child tree.
    gap = raw[MEMORY] - child_max
    if side["status"] == "ok":
        assert gap == 0
        assert side["buffer_peak_bytes"] == raw[MEMORY]
        assert side["spill_peak_bytes"] == raw[SPILL]
    else:
        assert gap > 0
    rss = side["measured_rss_sampled_peak_bytes"]
    assert rss > 0 and side["measured_rss_samples"] > 0
    decision = {}
    if engine == "outeryan":
        lines = [x for x in prefix.with_suffix(".trace").read_text().splitlines()
                 if x.startswith("[OY_DECISION]")]
        assert len(lines) == 1
        decision = dict(x.split("=", 1) for x in lines[0].split()[1:] if "=" in x)
        assert decision["outer_yan_selected"] == "1", (index, decision)
    groups = {}
    for group in PHASES:
        ops = [n for n in nodes if phase(n) == group]
        groups[group] = dict(operator_count=len(ops),
                            buffer_peak_bytes=max((n[MEMORY] for n in ops), default=None),
                            spill_peak_bytes=max((n[SPILL] for n in ops), default=None))
    return dict(buffer_peak_bytes=raw[MEMORY], rss_peak_bytes=rss,
                spill_peak_bytes=raw[SPILL], rss_samples=side["measured_rss_samples"],
                profiled_wall_s=raw["latency"], phases=groups, decision=decision,
                original_status=side["status"], root_child_gap_bytes=gap,
                profile=str(path.resolve()), profile_sha256=sha(path))


def pair_stats(rows, key):
    ratios = [r["outeryan"][key] / r["duckdb"][key] for r in rows]
    return dict(n=len(rows), geomean_ratio=math.exp(statistics.mean(map(math.log, ratios))),
                median_ratio=statistics.median(ratios), min_ratio=min(ratios), max_ratio=max(ratios),
                lower=sum(x < 1 for x in ratios), equal=sum(x == 1 for x in ratios),
                higher=sum(x > 1 for x in ratios), within_5pct=sum(0.95 <= x <= 1.05 for x in ratios),
                duckdb_median_mib=statistics.median(r["duckdb"][key] / MIB for r in rows),
                outeryan_median_mib=statistics.median(r["outeryan"][key] / MIB for r in rows),
                duckdb_max_mib=max(r["duckdb"][key] / MIB for r in rows),
                outeryan_max_mib=max(r["outeryan"][key] / MIB for r in rows))


def write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def collect(args):
    journal = [json.loads(x) for x in (args.run / "queries.jsonl").read_text().splitlines()]
    cohort_path = Path(__file__).with_name("memory_cohort_20261013.json")
    cohort = json.loads(cohort_path.read_text())
    metadata = json.loads((args.run / "run.json").read_text())
    assert sha(cohort_path) == metadata["cohort_sha256"]
    assert len(journal) == len(cohort["queries"]) == 281
    assert metadata["warmups_per_engine"] == metadata["measurements_per_engine"] == 1
    assert metadata["timeout_seconds_per_execution"] == 600 and not metadata["correctness_check"]
    with args.ids.open(newline="") as f:
        ids = {r["query"]: r for r in csv.DictReader(f)}
    rows, flat, warnings = [], [], []
    corpus = Path(__file__).parent / "outerjoin_benchmark/benchmark"
    for index, (record, pinned) in enumerate(zip(journal, cohort["queries"]), 1):
        assert record["query"] == pinned["query"]
        assert record["sql_sha256"] == pinned["sql_sha256"]
        sql_path = corpus / pinned["sql_path"]
        assert sha(sql_path) == pinned["sql_sha256"], sql_path
        query_id = ids[record["query"]]["short_query"]
        result = dict(index=index, query_id=query_id, query=record["query"], family=record["family"],
                      group=FAMILIES[record["family"]], sql_path=record["sql_path"],
                      graph_dataset=record["graph_dataset"], sql_sha256=record["sql_sha256"])
        for engine in ("duckdb", "outeryan"):
            result[engine] = audit_side(args.run, index, engine, record[engine], sql_path.read_text())
            if result[engine]["root_child_gap_bytes"]:
                warnings.append(dict(query_id=query_id, query=record["query"], engine=engine,
                                     original_status=record[engine]["status"],
                                     root_buffer_bytes=result[engine]["buffer_peak_bytes"],
                                     root_child_gap_bytes=result[engine]["root_child_gap_bytes"],
                                     note="Query total retained; child observations do not cover the exact root peak."))
        result["buffer_ratio"] = result["outeryan"]["buffer_peak_bytes"] / result["duckdb"]["buffer_peak_bytes"]
        result["rss_ratio"] = result["outeryan"]["rss_peak_bytes"] / result["duckdb"]["rss_peak_bytes"]
        if record.get("reference_off_s") is not None and record.get("reference_on_s"):
            result["reference_speedup"] = record["reference_off_s"] / record["reference_on_s"]
        rows.append(result)
    assert len({r["query_id"] for r in rows}) == 281
    rows.sort(key=lambda r: (list(FAMILIES).index(r["family"]), r["query_id"]))
    for r in rows:
        f = dict(query_id=r["query_id"], family=r["group"], graph_dataset=r["graph_dataset"])
        for engine in ("duckdb", "outeryan"):
            for metric in ("buffer_peak_bytes", "rss_peak_bytes", "spill_peak_bytes"):
                f[engine + "_" + metric.replace("_bytes", "_mib")] = r[engine][metric] / MIB
        f.update(buffer_ratio_outeryan_over_duckdb=r["buffer_ratio"], rss_ratio_outeryan_over_duckdb=r["rss_ratio"])
        for group in PHASES:
            val = r["outeryan"]["phases"][group]["buffer_peak_bytes"]
            f["outeryan_" + group + "_observed_buffer_peak_mib"] = None if val is None else val / MIB
            f["outeryan_" + group + "_operator_count"] = r["outeryan"]["phases"][group]["operator_count"]
        for engine in ("duckdb", "outeryan"):
            for key in ("original_status", "rss_samples", "root_child_gap_bytes", "profile"):
                f[engine + "_" + key] = r[engine][key]
        f.update(reference_speedup=r.get("reference_speedup"), query=r["query"], sql_path=r["sql_path"])
        flat.append(f)
    summaries = []
    for family, name in list(FAMILIES.items()) + [(None, "All")]:
        subset = [r for r in rows if family is None or r["family"] == family]
        summaries.append(dict(group=name, buffer=pair_stats(subset, "buffer_peak_bytes"),
                              rss=pair_stats(subset, "rss_peak_bytes"),
                              original_strict_pairs=sum(all(r[e]["original_status"] == "ok" for e in ("duckdb", "outeryan")) for r in subset),
                              sparse_rss_pairs=sum(any(r[e]["rss_samples"] < 3 for e in ("duckdb", "outeryan")) for r in subset)))
    report = dict(source_run=str(args.run.resolve()), journal_sha256=sha(args.run / "queries.jsonl"),
                  metadata=metadata, ratio_definition="OuterYan / DuckDB; lower means less memory",
                  query_count=len(rows), warnings=warnings, summaries=summaries, queries=rows,
                  limitations=["Buffer values are observed shared buffer-pool footprints, not exclusive allocations.",
                               "RSS is process memory sampled every 50 ms; short peaks can be missed.",
                               "Phase peaks use MAX, not SUM, and must not be stacked or normalized to 100%.",
                               "Root peaks may exceed all visible child observations; raw validator warnings are retained.",
                               "One warmup and one profiled measurement per engine; correctness not checked in this run.",
                               "Optional reference speedups come from separate timing inputs, not this memory run."])
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "memory_statistics.json").write_text(json.dumps(report, indent=2) + "\n")
    write_csv(args.out / "memory_by_query.csv", flat)
    write_csv(args.out / "memory_validation_warnings.csv", warnings)
    summary_flat = [dict(group=s["group"], metric=k, **s[k]) for s in summaries for k in ("buffer", "rss")]
    write_csv(args.out / "memory_summary.csv", summary_flat)
    notes = ["CPU9 memory comparison: " + args.run.name, "", *report["limitations"], "",
             f"Completed measured pairs: {len(rows)}; timeouts: 0; plan selections verified: {len(rows)}.",
             f"Original strict-validator complete pairs: {summaries[-1]['original_strict_pairs']}.",
             f"Root/child equality warnings: {len(warnings)}; query-level totals independently validated from raw JSON.",
             "Raw input files and previous performance statistics were not modified.", "",
             "Group | n | buffer ratio geometric mean | buffer ratio median | RSS ratio geometric mean | RSS ratio median"]
    for s in summaries:
        notes.append(f"{s['group']} | {s['buffer']['n']} | {s['buffer']['geomean_ratio']:.4f} | {s['buffer']['median_ratio']:.4f} | {s['rss']['geomean_ratio']:.4f} | {s['rss']['median_ratio']:.4f}")
    (args.out / "memory_analysis.txt").write_text("\n".join(notes) + "\n")
    print(json.dumps(dict(summaries=summaries, warning_count=len(warnings)), indent=2))
    return report


def figures(report, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.lines import Line2D
    import numpy as np

    plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"],
                         "font.size": 10, "axes.labelsize": 11, "axes.titlesize": 11,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "axes.axisbelow": True})
    rows = report["queries"]
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 5.0))
    for ax, key, title in zip(axes, ("buffer_peak_bytes", "rss_peak_bytes"),
                              ("(a) Observed buffer-pool peak", "(b) Sampled process RSS peak")):
        vals = [r[e][key] / MIB for r in rows for e in ("duckdb", "outeryan")]
        lo, hi = 10 ** math.floor(math.log10(min(vals))), 10 ** math.ceil(math.log10(max(vals)))
        ax.plot([lo, hi], [lo, hi], color="#777777", lw=1, zorder=1)
        for family, name in FAMILIES.items():
            subset = [r for r in rows if r["family"] == family]
            ax.scatter([r["duckdb"][key] / MIB for r in subset],
                       [r["outeryan"][key] / MIB for r in subset],
                       s=29, alpha=0.65, c=COLORS[family], edgecolors="white", linewidths=0.25,
                       label=f"{name} ({len(subset)})", zorder=3)
        ax.set(xscale="log", yscale="log", xlim=(lo, hi), ylim=(lo, hi),
               xlabel="DuckDB (MiB)", ylabel="OuterYan (MiB)", title=title)
        ax.set_aspect("equal")
        ax.grid(which="major", color="#E8E8E8", linewidth=0.6)
        ax.tick_params(direction="in", top=True, right=True, which="both")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.01))
    fig.text(0.5, 0.018, "281 paired queries | Below diagonal: OuterYan uses less memory | 1 MiB = 2²⁰ bytes",
             ha="center", fontsize=9)
    fig.subplots_adjust(left=.085, right=.985, bottom=.16, top=.88, wspace=.28)
    fig.savefig(out / "memory_comparison.pdf")
    fig.savefig(out / "memory_comparison.png", dpi=190)
    plt.close(fig)

    pages = 0
    with PdfPages(out / "memory_by_query.pdf") as pdf:
        for family, family_name in FAMILIES.items():
            subset = [r for r in rows if r["family"] == family]
            for offset in range(0, len(subset), 28):
                group = subset[offset:offset + 28]
                pages += 1
                fig, axes = plt.subplots(1, 2, figsize=(11.7, 8.3), sharey=True)
                for ax, key, title in zip(axes, ("buffer_peak_bytes", "rss_peak_bytes"),
                                          ("Observed buffer-pool peak", "Sampled process RSS peak")):
                    y = np.arange(len(group))
                    x0 = np.array([r["duckdb"][key] / MIB for r in group])
                    x1 = np.array([r["outeryan"][key] / MIB for r in group])
                    ax.hlines(y, x0, x1, color="#A6ACB5", lw=1.1, zorder=2)
                    ax.scatter(x0, y, s=24, color=ENGINE_COLORS[0], edgecolors="white", linewidths=.3, zorder=3)
                    ax.scatter(x1, y, s=24, color=ENGINE_COLORS[1], edgecolors="white", linewidths=.3, zorder=3)
                    ax.set(xscale="log", xlabel="Memory (MiB; logarithmic scale)", title=title)
                    ax.set_yticks(y, [r["query_id"] for r in group])
                    ax.set_ylim(len(group) - .25, -.75)
                    ax.grid(axis="x", which="major", color="#E8E8E8", lw=.6)
                    ax.tick_params(axis="y", length=0, labelsize=9)
                    ax.text(1.025, 1.01, "OY / DB", transform=ax.transAxes, fontsize=8, ha="left")
                    for yy, ratio in enumerate(x1 / x0):
                        ax.text(1.025, yy, f"{ratio:.2f}×", transform=ax.get_yaxis_transform(),
                                va="center", fontsize=8, color="#40464F", clip_on=False)
                    ax.spines[["right", "top"]].set_visible(False)
                handles = [Line2D([], [], marker="o", ls="", color=c, label=e)
                           for c, e in zip(ENGINE_COLORS, ("DuckDB", "OuterYan"))]
                fig.legend(handles=handles, loc="upper right", bbox_to_anchor=(.92, .985), frameon=False, ncol=2)
                fig.text(.11, .955, f"{family_name}  |  queries {offset + 1}–{offset + len(group)} of {len(subset)}", fontsize=13)
                fig.text(.11, .04, "Ratios < 1 mean lower OuterYan memory. RSS sampling interval: 50 ms; brief peaks may be missed.", fontsize=8)
                fig.text(.94, .04, str(pages), ha="right", fontsize=8)
                fig.subplots_adjust(left=.115, right=.91, top=.87, bottom=.11, wspace=.35)
                pdf.savefig(fig)
                plt.close(fig)
    print(f"Wrote 2 PDF figures; per-query comparison has {pages} pages and {len(rows)} labeled queries.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--ids", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    figures(collect(args), args.out)


if __name__ == "__main__":
    main()
