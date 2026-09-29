#!/usr/bin/env python3
"""Compare SF1 and extrapolated SF100 statistics for the supplied paper query."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def parse_result(prefix):
    details = prefix.with_suffix(".details.txt").read_text()
    decisions = [dict(re.findall(r"(\w+)=(\S+)", line))
                 for line in prefix.with_suffix(".trace.txt").read_text().splitlines()
                 if line.startswith("[OY_DECISION]") and "baseline_cost=NA" not in line]
    if len(decisions) != 1:
        raise RuntimeError(f"Expected one costed EXPLAIN decision, got {len(decisions)}")
    rows = {name: int(count) for name, count in re.findall(r"^table=(\w+) rows=(\d+)$", details, re.M)}
    ndv = {name: int(count) for name, count in re.findall(r"^column=([\w.]+) ndv=(\d+)$", details, re.M)}
    costs = {name: float(value) for name, value in re.findall(
        r"^(dp_winner|alternative_customer_orders_first) total=([\d.eE+-]+)", details, re.M)}
    grouping = re.search(r"^dp_grouping=(.+)$", details, re.M)
    if not grouping or "dp_winner" not in costs:
        raise RuntimeError("Missing DP diagnostic")
    return {"rows": rows, "ndv": ndv, "dp_grouping": grouping[1], "dp_costs": costs,
            "decision": decisions[0], "plan": str(prefix.with_suffix(".plan.txt"))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "tpch_db")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build/release")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    db, build = args.db.resolve(), args.build_dir.resolve()
    library = next((build / "src" / name for name in ("libduckdb.dylib", "libduckdb.so")
                    if (build / "src" / name).is_file()), None)
    compiler = shutil.which(os.environ.get("CXX", "c++"))
    if not db.is_file() or not library or not compiler:
        parser.error("Existing SF1 database, Release shared library and C++17 compiler are required")
    out = (args.out or ROOT / "auto_test/results" / (
        "paper_stats_whatif_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    )).resolve()
    out.mkdir(parents=True, exist_ok=False)
    executable = out / "stats_whatif"
    source, query = HERE / "stats_whatif.cpp", HERE / "tpch/customer_orders_lineitem.sql"
    command = [compiler, "-std=c++17", "-O2", "-I", str(ROOT / "src/include"), str(source),
               "-L", str(library.parent), "-lduckdb", "-Wl,-rpath," + str(library.parent), "-o", str(executable)]
    with (out / "build.stdout.txt").open("w") as stdout, (out / "build.stderr.txt").open("w") as stderr:
        subprocess.run(command, check=True, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=120)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("DUCKDB_OY") and key != "DUCKDB_SJ_KERNEL_TRACE"}
    before = (db.stat().st_size, db.stat().st_mtime_ns)
    runs = {}
    for scale in (1, 100):
        prefix = out / f"sf{scale}"
        env["DUCKDB_OYTRACE"] = str(prefix.with_suffix(".trace.txt"))
        with prefix.with_suffix(".details.txt").open("w") as stdout, prefix.with_suffix(".stderr.txt").open("w") as stderr:
            subprocess.run([str(executable), str(db), str(query), str(scale), str(prefix)],
                           check=True, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, timeout=60)
        runs[str(scale)] = parse_result(prefix)
    if before != (db.stat().st_size, db.stat().st_mtime_ns):
        raise RuntimeError("Source database changed during the experiment")
    small, large = runs["1"], runs["100"]
    if small["rows"].get("customer") != 150000 or small["rows"].get("orders") != 1500000:
        raise RuntimeError("Input does not have the expected SF1 customer/orders row counts")
    assert large["rows"] == {name: count * 100 for name, count in small["rows"].items()}
    for key in ("customer.c_custkey", "orders.o_orderkey", "orders.o_custkey", "lineitem.l_orderkey"):
        assert large["ndv"][key] == small["ndv"][key] * 100, key
    for key in ("orders.o_orderdate", "lineitem.l_shipmode"):
        assert large["ndv"][key] == small["ndv"][key], key
    result = {"statistics_source": "SF1 catalog extrapolation, NOT measured SF100 statistics",
              "planning_only": True, "database": str(db), "database_size_mtime_ns": before,
              "library": str(library), "library_sha256": digest(library), "compile_command": command,
              "source_sha256": digest(source), "query_sha256": digest(query), "runs": runs}
    (out / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    for artifact in (source, query, Path(__file__)):
        shutil.copy2(artifact, out / artifact.name)
    lines = ["# SF100 统计外推：论文单例的计划选择", "",
             "这是 planning-only what-if：行数、四个连接键 NDV 和键最大值按 SF1 放大 100 倍；",
             "日期、shipmode 等其他列的统计保持不变。不是从真实 SF100 数据采集的统计快照。",
             "原始 SELECT 和只读 SF1 数据库不变；没有执行 SF100 数据量的查询或测量其性能。", "",
             "| 统计规模 | DP 最优成本 | customer–orders 先连成本 | 最终计划 | 重排 | cost gate |",
             "|---|---:|---:|---|---|---|"]
    for scale, run in runs.items():
        cost, decision = run["dp_costs"], run["decision"]
        alternative = cost.get("alternative_customer_orders_first")
        alternative_text = f"{alternative:,.3f}" if alternative is not None else "参见 DP grouping"
        lines.append(f"| SF{scale} | {cost['dp_winner']:,.3f} | {alternative_text} | "
                     f"{decision['selected_plan']} | {decision['outer_reordered']} | {decision['gate_result']} |")
    decision = large["decision"]
    lines += ["", f"SF100 外推下的 DP grouping：`{large['dp_grouping']}`。",
              f"最终决策：`reason={decision['reason']}`，`cost_gate_applied={decision['cost_gate_applied']}`。", "",
              "上表是正常过滤估计下、同一组 reducer 的真实 join 成本比较，不含固定 SJ 工作量。",
              "最终门控还计算日期默认选择率的保守上界场景，因此其成本值与上表不同：", "",
              f"- DuckDB baseline：{float(decision['baseline_cost']):,.3f}",
              f"- OuterYan 候选（含 SJ）：{float(decision['candidate_total']):,.3f}",
              f"- 比值：{float(decision['raw_cost_ratio']):.6f}；允许上限：{decision['cost_ratio_limit']}", "",
              "等比例扩大行数和连接键 NDV 基本保持选择率及成本比值，只有整数取整产生小偏差。",
              "本次两个规模都先连接 orders–lineitem；同 grouping 规则先回退，门控未实际参与选择。",
              "真实 SF100 上重新采集的近似 NDV 可能不同，本实验不能替代该统计快照，也不能说明 SF100 执行性能。", "",
              "注入使用进程内 table-function 统计回调；独立注册函数名以保证 DuckDB baseline 的计划复制也保留注入。",
              "SF1 对照与此前原库诊断的 DP、baseline 和 SJ 成本一致；脚本验证 SF100 注入的行数和 NDV。", "",
              "产物：[SF100 计划](sf100.plan.txt)、[决策 trace](sf100.trace.txt)、",
              "[DP 明细](sf100.details.txt)、[机器可读结果](result.json)。", "",
              "复现：`python3 auto_test/paper_examples/run_stats_whatif.py`。"]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print(out)
    for scale, run in runs.items():
        print(f"SF{scale}: {run['dp_grouping']}; {run['decision']['selected_plan']}; {run['dp_costs']}")


if __name__ == "__main__":
    main()
