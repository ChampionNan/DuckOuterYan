# DuckOuterYan：论文实验部分

[`sections_6_7.tex`](sections_6_7.tex) 是可直接接入论文的英文 LaTeX 片段，
其中实验部分已按以下四个小节组织：

1. Overall Performance：总览图、按 benchmark 汇总表和分析；
2. Representative Phase-Time Breakdown：阶段图、全量 phase 汇总表和案例分析；
3. Effect of Input-Tree Shape：shape 汇总表和分析；
4. Optimization Time：与 Yannakakis+ 相近的表格结构和待采集指标。

当前 v1 已更新为 `v1-mixed-20260922`：206 条 query（170 条
benchmark-derived structures + 36 条 controls），join labels 不再沿用旧的
FULL-heavy 设计。V2 有 546 条主 workload，另有 84 条单独报告的 wide-range
selectivity ablation。三者都尚无与当前 SQL 对应的完整结果，因此正文结果区暂不引用
任何性能数字。

## 接入论文

主文件导言区需要：

```latex
\usepackage{amsmath,amssymb,booktabs,graphicx}
```

从仓库根目录编译时：

```latex
\input{auto_test/paper/sections_6_7}
```

下面的目录只保存旧版图形，当前正文不会引用它：

```text
auto_test/results/plots/20260916_211812/t32/
```

旧目录包含两张曾使用的投稿图：

- `speedup_all_queries.pdf`：旧 FULL-heavy 版本 176 条有效 query 的 overall performance；
- `phase_breakdown_outeryan.pdf`：32 条代表 query 的 phase 与 runtime 对照。

`runtime_outeryan_queries` 已取消，不再被论文引用。若把文件复制到 Overleaf，上传
上述两张 PDF，并在 `\input` 前覆盖图目录：

```latex
\newcommand{\DuckOuterYanFigureDir}{figures}
\input{sections_6_7}
```

正文继续使用原稿的 `tpch`、`tpcds`、`job`、`sqlstorm25` BibTeX key。

## 每次实验的统计信息在哪里

一次完整画图会在对应 run 目录同时写出四类可追溯结果：

| 文件 | 内容 | 用途 |
|---|---|---|
| `experiment_onoff_*.csv` | 每条 query 的 OFF/ON median、selected plan、profile 字段 | 原始事实来源 |
| `STATISTICS.md` | 自动生成的可读汇总，包括 family、shape、selected/fallback、phase 表 | 人工检查和填写论文表格 |
| `statistics.json` | 与 Markdown 相同口径的完整精确数值和方法元数据 | 程序化制表，避免从图片抄数 |
| `phase_queries.json` | phase 图中具体 query、短名、顺序、CPU 分段、wall time 与 baseline | 核对代表案例和 caption |

旧版文件的具体位置是（仅用于 provenance，不可填写当前论文表格）：

- 原始数据：`auto_test/results/experiment_onoff_benchmark_20260916_211812_t32.csv`；
- 可读统计：`auto_test/results/plots/20260916_211812/t32/STATISTICS.md`；
- 机器可读统计：`auto_test/results/plots/20260916_211812/t32/statistics.json`；
- phase 样本映射：`auto_test/results/plots/20260916_211812/t32/phase_queries.json`。

旧版数值来自上述 `STATISTICS.md`/`statistics.json`。它们已从当前可编译结果区
移除；完成 mixed-v1 实验后，需要把新统计同步到 `sections_6_7.tex`。图本身由脚本
直接刷新。

## 旧结果的复现命令（不可作为 mixed-v1 结果）

在仓库根目录执行：

```bash
MPLCONFIGDIR=/tmp/outeryan-mpl python3 auto_test/plot_speedup.py \
  auto_test/results/experiment_onoff_benchmark_20260916_211812_t32.csv \
  -o auto_test/results/plots/20260916_211812/t32/outeryan_benchmark_figures_t32.pdf \
  --split-output-dir auto_test/results/plots/20260916_211812/t32 \
  --statistics-dir auto_test/results/plots/20260916_211812/t32
```

该命令同时更新两张独立 PDF/PNG、合并预览 PDF、`STATISTICS.md`、
`statistics.json` 和 `phase_queries.json`。脚本会优先使用主 CSV；只有主文件缺 query
时才从 `.attempts.csv` 补齐，并以 family + query 去重，主 CSV 的最终行优先。

## 当前实验口径

- OFF：仅禁用 `outer_yan`；ON：启用 V7 gated policy，其余设置相同；
- 每个配置先执行 1 次不计时 warm-up，再执行 3 次计时，报告 median wall time；
- 计时覆盖 optimization、execution 和完整结果消费，但不含进程启动及 session 设置；
- runtime 测量关闭 profiler；phase 使用单独的 ON profile 批次；
- phase 的 Round 1/2/3/Other 是跨线程累积 operator CPU work，和等于 profile CPU
  total，不能与 wall time 直接相加或解释为 wall-time 百分比；
- speed-up 为 DuckDB / DuckOuterYan；geomean 对 query 等权，Total 为
  `sum(OFF) / sum(ON)`。

这与 Yannakakis+ 的 warm-cache、重复执行取 median 的原则一致，但当前数据是
1 warm-up + 3 measured，而 Yannakakis+ 原文使用 10 次执行。因此正文只称 measurement
principle 一致，不宣称重复次数完全相同。若论文要求逐项复现其 10 次口径，需要修改
harness 对奇数 `--runs` 的限制并重新运行，不能从现有三次结果补算。

当前 CSV 只保存 runtime median，没有保存三个 runtime sample；phase 列中的
`profile_timed_samples=3` 可核对 profile 重复数。今后的结果若要逐次审计，应同时保留
harness `.txt` 日志或把每次 runtime sample 增加为 CSV/JSON 字段。

## 已作废的旧结果快照

- 这些数字仅对应 0916 FULL-heavy SQL，不对应当前 v1；
- 176 条有效 query；55 条选择 OuterYan，121 条保留 native plan；
- 全 workload：geomean `1.205132×`，total-time speed-up `1.335485×`；
- OFF/ON median 总和：`6303.561926 s / 4720.055300 s`，节省
  `1583.506625 s`（25.120823%）；
- 55 条 selected query：geomean `1.835706×`，total `2.609079×`；
- 当前 CSV SHA-256：
  `afbd92a0f3c8c82b420999f241711e468fd0a5f83ecae4a44aca75531d8bf470`。

## 尚未完成的 Optimization Time

0916 CSV 没有 `CUMULATIVE_OPTIMIZER_TIMING` 与 `OPTIMIZER_OUTER_YAN` 的独立采样，
所以不能从 end-to-end runtime 反推 optimizer latency。论文中的 optimization-time 表
保留为明确的 `--`，而不是填入估计值。后续应对 OFF/ON 分别运行 detailed profiler，
记录总 optimizer time，并在 ON 下额外记录 OuterYan pass time；仍采用 warm-up 后三次
测量取 median，并与 runtime/phase profiling 分开执行。

## 投稿前核对

- 确认论文服务器仍是 Xeon Silver 4116、24 cores/48 hardware threads、192 GB；
- 补齐 OS、commit、compiler、storage、memory/spill 设置及 JOB/graph snapshot；
- 生成 optimization-time CSV 后填充 Table `tab:optimization-time`；
- V2 和 selectivity ablation 完整跑完后，再新增对应结果表或 ablation 图；
- 在论文主工程中编译并检查浮动体位置、跨页表格和外部交叉引用。
