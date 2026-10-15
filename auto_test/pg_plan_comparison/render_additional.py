#!/usr/bin/env python3
"""Render measured C/D results and profiled plans without using profile timings."""

import argparse
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import textwrap

from plans import REAL_JOINS, duck_tree, nodes, semantic


MODES = {"PG": "PG-Plan", "native": "DuckDB", "OY": "OuterYan"}
PROFILE_NAMES = {
    "PG": ("PG.profile.json", "PG-Replay.profile.json"),
    "native": ("native.profile.json", "DuckDB.profile.json"),
    "OY": ("OY.profile.json", "OuterYan.profile.json"),
}
CASES = {"case_c": "Case C: JOB 21a", "case_d": "Case D: JOB 11a"}
COLORS = {"PG": "#fff1db", "native": "#e9f1ff", "OY": "#e4f4e9"}


def load(path):
    return json.loads(path.read_text())


def walk(node):
    yield node
    for child in node.get("children", []):
        yield from walk(child)


def sql_text(text):
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("--")).strip().rstrip(";").strip()


def read_profiles(directory, query):
    profiles = {}
    for mode, filenames in PROFILE_NAMES.items():
        path = next((directory / name for name in filenames if (directory / name).exists()), None)
        if path is None:
            continue
        profile = load(path)
        if sql_text(profile.get("query_name", "")) != sql_text(query):
            raise ValueError(f"profile query differs from bare query: {path}")
        if len(profile.get("children", [])) != 1:
            raise ValueError(f"expected one profile root: {path}")
        tree = duck_tree(profile["children"][0], True)
        joins = [node for node in nodes(tree) if node["op"] == "join"]
        profiles[mode] = {
            "profile": profile,
            "tree": tree,
            "metrics": {
                "real_join_input_rows": sum(node["input_rows"] for node in joins),
                "max_nonroot_intermediate_rows": max(
                    (node["output_rows"] for node in joins[1:]), default=0),
                "result_rows": profile["rows_returned"],
                "sj_operator_count": sum(
                    str(node.get("operator_name", "")).strip().startswith("SJ_")
                    for node in walk(profile)),
            },
        }
    return profiles


def final_medians(record, profiles):
    """A summary file certifies completion; validate its raw unprofiled samples."""
    if set(profiles) != set(MODES):
        raise ValueError("completed measurement is missing one or more mode profiles")
    correctness = record.get("correctness", {})
    if correctness.get("exact_four_way_multiset_equality") is not True:
        raise ValueError("completed measurement lacks exact four-way result validation")
    medians = {}
    sample_counts = set()
    for mode in MODES:
        samples = record["runs"][mode]
        if (len(samples) < 3 or any(isinstance(value, bool) or not isinstance(value, (int, float))
                                   or not math.isfinite(value) or value <= 0 for value in samples)):
            raise ValueError(f"invalid unprofiled timing samples for {mode}")
        sample_counts.add(len(samples))
        medians[mode] = statistics.median(samples)
        if not math.isclose(medians[mode], record["median_ms"][mode], rel_tol=1e-9, abs_tol=1e-6):
            raise ValueError(f"stored median does not match samples for {mode}")
        expected = correctness["results"][mode]["rows"]
        if profiles[mode]["metrics"]["result_rows"] != expected:
            raise ValueError(f"profile cardinality differs from validated result for {mode}")
        if semantic(profiles[mode]["tree"]) != record["plans"][mode]["semantic"]:
            raise ValueError(f"profile semantic tree differs from summary for {mode}")
    if len(sample_counts) != 1:
        raise ValueError("modes have different numbers of timing samples")
    return medians, sample_counts.pop()


def description(node):
    name = node.get("operator_name", "").strip()
    info = node.get("extra_info", {})
    lines = []
    if name in {"SEQ_SCAN", "TABLE_SCAN"}:
        lines.append(info.get("Table", "scan").split(".")[-1])
    elif name in REAL_JOINS:
        lines.append(info.get("Join Type", "") + " " + name)
    elif name.startswith("SJ_"):
        lines.append(name.replace("_ROUND_", " R").replace("SJ_", "SJ "))
    else:
        lines.append(name)
    for key in ("Conditions", "Expression", "Filters"):
        value = info.get(key)
        if value:
            values = value if isinstance(value, list) else [value]
            for expression in values:
                lines.extend(textwrap.wrap(str(expression), width=34, break_long_words=False))
    count = node.get("operator_cardinality")
    if type(count) is not int or count < 0:
        raise ValueError("operator is missing an actual row count")
    lines.append(f"rows: {count:,}")
    return "\n".join(lines)


def draw_plans(case, profiles, medians, runs, directory, dot):
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    lines = ["digraph plans {", 'graph [rankdir=TB, bgcolor="white", pad=0.2,',
             '  nodesep=0.16, ranksep=0.28, pack=true, packmode="array_u3",',
             '  fontname="Helvetica", fontsize=16, labelloc=t,',
             f"  label={quote(CASES[case] + ' — actual executed plans')}];",
             'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10,',
             '  color="#596579", fillcolor="white", margin="0.08,0.06"];',
             'edge [color="#68778c", arrowsize=0.55];']
    for index, (mode, title) in enumerate(MODES.items()):
        label = title
        label += (f"\n{medians[mode]:,.3f} ms; {runs} unprofiled runs" if medians else
                  "\nprofile for plan inspection; no final runtime")
        lines.extend([f"subgraph cluster_{index} {{", f"label={quote(label)};",
                      f'color="{COLORS[mode]}"; style="rounded,filled"; fillcolor="{COLORS[mode]}";'])
        serial = 0

        def emit(node):
            nonlocal serial
            children = node.get("children", [])
            if node.get("operator_name", "").strip() == "PROJECTION" and len(children) == 1:
                return emit(children[0])
            name = f"m{index}n{serial}"
            serial += 1
            color = "#f0e8fa" if node.get("operator_name", "").strip().startswith("SJ_") else "white"
            lines.append(f"{name} [label={quote(description(node))}, fillcolor={quote(color)}];")
            for position, child in enumerate(children):
                child_name = emit(child)
                side = f' [label="{position + 1}"]' if len(children) > 1 else ""
                lines.append(f"{name} -> {child_name}{side};")
            return name

        if mode in profiles:
            emit(profiles[mode]["profile"]["children"][0])
        else:
            lines.append(f'm{index}n0 [label="Profile not captured"];')
        lines.append("}")
    lines.append("}")
    path = directory / f"{case}_plans.dot"
    path.write_text("\n".join(lines) + "\n")
    if dot:
        for extension in ("svg", "png"):
            subprocess.run([dot, f"-T{extension}", str(path), "-o",
                            str(path.with_suffix("." + extension))], check=True)
    return path.with_suffix(".svg") if dot else path


def evidence_text(capture, case):
    if capture is None or not (capture / case / "search_space_evidence.json").exists():
        return "PG search-space evidence was not supplied to this renderer."
    evidence = load(capture / case / "search_space_evidence.json")
    if evidence.get("status") == "two_base_group_rejected":
        group = ", ".join(evidence["group"])
        return (f"PG trace rejects the two-base grouping {{{group}}} used by OuterYan. "
                "The recorded rejection, rather than different final plans alone, establishes this witness.")
    if evidence.get("status") == "crosses_full_barrier":
        return "PG trace records a FULL-join boundary crossed by an OuterYan grouping."
    return "PG search-space exclusion remains unproven for this case."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--capture", type=Path, help="optional capture_additional output with PG traces")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    summary_path = args.results / "summary.json"
    summary = load(summary_path) if summary_path.exists() else None
    environment_path = args.results / "environment.json"
    environment = load(environment_path) if environment_path.exists() else {}
    dot = shutil.which("dot")
    report = ["# Additional PostgreSQL plan comparisons", "",
              "These two targeted JOB examples were selected to investigate stronger improvements; "
              "they are not a representative workload sample.", "",
              "PG-Plan imports PostgreSQL's typed logical join tree and executes it in DuckDB. "
              "DuckDB uses its native optimizer with OuterYan disabled; OuterYan uses normal cost-gated selection. "
              "The PG physical executor is used separately for correctness.", ""]
    if environment:
        report += [f"Settings: {environment.get('threads', 'unrecorded')} thread(s), "
                   f"{environment.get('memory_limit', 'unrecorded')} memory limit. "
                   f"Measurement: {environment.get('timing', environment.get('purpose', 'unrecorded'))}.", ""]
    if summary is None:
        report += ["**Incomplete measurement:** no `summary.json` is present. "
                   "This report shows captured plan shapes and actual row counts only; "
                   "profile latency is not a final runtime or speedup.", ""]
    report += ["Diagram edges 1 and 2 retain the physical child order. Unary projections are hidden; "
               "filters and semi-join (SJ) operators remain visible. Rows are actual profile cardinalities. "
               "Real-join input totals sum both child cardinalities of each ordinary join; "
               "they exclude SJ work. Reported unprofiled runtimes include SJ work and full result draining.", ""]
    rendered = {}
    for case, title in CASES.items():
        directory = args.results / case
        if not (directory / "query.sql").exists():
            continue
        query = (directory / "query.sql").read_text()
        profiles = read_profiles(directory, query)
        if not profiles:
            continue
        medians, runs = (final_medians(summary[case], profiles) if summary is not None else (None, None))
        diagram = draw_plans(case, profiles, medians, runs, args.out, dot)
        report += [f"## {title}", "", "```sql", sql_text(query) + ";", "```", ""]
        if medians:
            report += [f"Runtime medians from {runs} interleaved, unprofiled executions per mode; "
                       "the full result multiset matches across the three DuckDB modes and native PostgreSQL.", "",
                       "| Plan | Median (ms) | Speedup of OuterYan |", "|---|---:|---:|"]
            for mode, name in MODES.items():
                ratio = f"{medians[mode] / medians['OY']:.3f}×" if mode != "OY" else "—"
                report.append(f"| {name} | {medians[mode]:,.3f} | {ratio} |")
            report.append("")
        report += [f"![{title}: executed plans]({diagram.name})" if dot else
                   f"[Graphviz plan source]({diagram.name}) (install Graphviz to render SVG/PNG).", "",
                   "| Plan | Real-join input rows | Largest non-root join output | Result rows | SJ operators |",
                   "|---|---:|---:|---:|---:|"]
        for mode, item in profiles.items():
            metrics = item["metrics"]
            report.append("| " + MODES[mode] + " | " + " | ".join(
                f"{metrics[key]:,}" for key in ("real_join_input_rows", "max_nonroot_intermediate_rows",
                                               "result_rows", "sj_operator_count")) + " |")
        report += ["", evidence_text(args.capture, case), ""]
        if "OY" in profiles:
            early_pair = {"company_name", "movie_companies"}
            def tables(tree):
                return {node["relation"] for node in nodes(tree) if node["op"] == "scan"}
            early = any(node["op"] == "join" and tables(node) == early_pair
                        for node in nodes(profiles["OY"]["tree"]))
            if early:
                report += ["OuterYan joins the filtered company names to movie-company rows early. "
                           "This lets the selective company condition take effect before the remaining "
                           "movie annotations are combined; SJ reduction also contributes where shown. "
                           "The measured join-input and intermediate-row counts quantify the resulting work. "
                           "The gain must therefore be attributed to the complete selected plan, including SJ work.", ""]
        for mode, item in profiles.items():
            report += [f"{MODES[mode]} semantic tree (SJ wrappers omitted):", "", "```text",
                       semantic(item["tree"]), "```", ""]
        rendered[case] = {"metrics": {mode: item["metrics"] for mode, item in profiles.items()},
                          "median_ms": medians, "timed_runs_per_mode": runs}
    if not rendered:
        raise ValueError("no C/D profiles with their original queries were found")
    (args.out / "report.md").write_text("\n".join(report))
    (args.out / "rendered_metrics.json").write_text(json.dumps(rendered, indent=2) + "\n")
    print(args.out / "report.md")


if __name__ == "__main__":
    main()
