# DuckOuterYan：Section 6 / Section 7

`sections_6_7.tex` 是可直接替换原两节的英文 LaTeX 正文片段，不含
`\documentclass` 或 `document` 环境，不改原论文其它章节，也不强制章节编号。
放在前五节之后即可成为第 6、7 节。

## 接入

主文件导言区需要：

```latex
\usepackage{amsmath,amssymb,booktabs,graphicx}
```

从仓库根目录编译时：

```latex
\input{auto_test/paper/sections_6_7}
```

默认引用现有 `auto_test/results/plots/20260908_235240/t32/` 中的三张 PDF，
没有复制图或另建 sample 目录。若移入 Overleaf，将该目录中的
`speedup_all_queries.pdf`、`runtime_outeryan_queries.pdf`、
`phase_breakdown_outeryan.pdf` 上传至论文的 `figures/`，并在 `\input` 前加：

```latex
\newcommand{\DuckOuterYanFigureDir}{figures}
\input{sections_6_7}
```

沿用原稿的 `tpch`、`tpcds`、`job`、`sqlstorm25` 四个 BibTeX key。
没有杜撰新的文献条目。主文件需要已有的对应 `.bib`。

## 修改内容

- Section 6：用 5 个核心公式代替递归状态、集合签名和多层步骤符号；
  保留基数假设、两轮更新顺序、成本项、连接树枚举和当前 V7 选择逻辑。
  当前源代码的门限为普通 1.0、低保留率 0.9、受限 stretch 1.2；
  stretch 的 real-join input ratio 上限是 **0.30**，不是较早说明里的 0.75。
- Section 7 第一小节新增 **DuckOuterYan System Design**，说明候选生成、
  决策、下放执行、bitmap/hash 筛选和流水线依赖。OuterYan 保留为算法名称，
  DuckOuterYan 是集成系统名；正文解释现有图中的 ON 标签 OuterYan。
- 只报告当前 32 线程；删除旧的单线程表格和错误的 178 selected 口径。
  176 条有效查询与 55 条 selected 分开报告，32 条图中样本不用于总体统计。
- 统计表不列 min。保留 geomean、mean、median、max、total-time ratio，
  并解释加速比聚合方式。shape 表保留计数、选择数与主要汇总指标。
- 更新 170 core、36 supplementary、206 full union、185 run input、
  176 completed、144 completed core + 32 supplementary 的关系。
  不再将补充集误写成 170 条真实工业查询，披露历史 performance-selected 来源。
- 核心集独立结果：geomean 1.1877093914、total-time ratio 1.3044014876。
  补充集独立结果：1.2926688942、2.0626781995。混合集不是标准原生 benchmark。
- 9 个 32 线程超时仍作为原始运行的失败覆盖披露；不把活动清单删减写成
  原实验没有超时，也不声称 graph bushy / TPC-H star 覆盖仍然完整。

## 证据与版本范围

- 计时数据：`../results/experiment_onoff_benchmark_20260908_235240_t32.csv`
  和同名 `.attempts.csv`。两份都是 185 条且内容相同，按 family + query 去重。
  SHA-256 均为 `13da9290087eafe71634dae2ff8a30d88acceccaf3e7930d68137517616c5cfc`。
- 文件名包含 0908，但 `.txt` 首行记载此 t32 批次启动于 **2026-09-10 07:56:12**。
  正文因此称“32-thread run”，不把文件名当作精确测量日期。
- 日志直接确认 release 路径、32 threads、TPC-H/TPC-DS SF=100、graph=bitcoin、
  1 warm-up + 3 timed、未开启 profile、1800 秒限额、无重试。
- `../build_db.sh` 将 bitcoin 映射为 SNAP Bitcoin Alpha，取 src/dst 建立各图关系。
  当前日志没有数据文件哈希，正文不虚构 snapshot 或精确边数。
- `../outerjoin_benchmark/benchmark/manifest.csv` 用于核对 144/32 来源及 selected 统计。
- 样本与旧 profile 来自 `../results/plots/20260908_235240/t32/` 的
  `representative_queries.json`、`phase_queries.json`，已按完整查询名核对。
- 实现依据：`src/optimizer/outer_yan/pipeline/outer_yan_{pre,dp,optimizer,post}.cpp`、
  对应头文件、`physical_sj_{build,probe}.cpp` 和实际实验日志。

## 投稿前仍需补齐

1. **当前 32 线程 profile 尚不存在。** Breakdown 的图、正文和 caption
   都明确为 2026-08-30、48 线程的历史占位。Baseline 也来自同次旧 48 线程实验，
   不与当前 32 线程 timing 拼接。旧/新记录仅按名称对齐，不能证明服务器 SQL
   字节一致。新 profile 到达后需同步替换图与分段分析。
2. 原稿的 Xeon Silver 4116 / 24 核 / 48 硬件线程 / 192 GB 作为
   “reported server configuration”保留；需确认仍对应当前服务器。
   OS、实际测试 commit/patch version、编译器、存储、memory limit/spill、
   JOB/graph snapshot 未记录，不能从笔记本环境补写。
3. 本机没有发现 LaTeX 编译器；本轮做源码、数值、标签/图引用和结构检查，
   不声称已完成整篇论文的排版编译。图沿用已渲染检查的当前 t32 输出。

## 引用兼容性

保留原主要 section/table/figure labels。`sec:two-round-reduction` 和
`sec:plan-enumeration` 现在指向合并后的同一小节。
删除旧 `fig:runtime-outeryan-job`，JOB 已并入 `fig:runtime-outeryan-queries`。
原 `fig:outerjoin-benchmark-construction` 改为 benchmark 小节中的构造说明，
外部引用改指 `sec:outerjoin-benchmark`。
新增 `sec:system-design`、`sec:plan-selection`、`fig:speedup-all-queries`。
新的 `eq:join-cardinality` 合并旧的 inner/unmatched/outer cardinality 公式；
若其它章节引用原细分公式标签，应改为这个标签。删除的 DP 状态、递推和 grouping
signature 公式改为文字，外部引用应改指 `sec:plan-enumeration` 或
`sec:plan-selection`。`eq:edge-ndv` 改指 `sec:cardinality-estimation`，
`eq:semijoin-ndv` 改指 `sec:two-round-reduction`，`eq:plan-selection`
改指 `sec:plan-selection`。源码未保留 `\fix`、`\bingnan` 或旧的注释算法。

本轮核对了全部 10 行 family 表、4 行 category 表、核心/补充集独立统计、
32 个样本的 profile 身份，以及 25 个唯一标签、内部引用和三张图的路径。
其它章节的交叉引用需在原论文工程中按上述映射检查。
