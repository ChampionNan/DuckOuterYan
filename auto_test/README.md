# `auto_test/` — OuterYan correctness and performance suite

This directory contains the operational test harness for the OuterYan optimizer.
Use a release build for performance runs. A debug build is useful for assertions,
but its timings are only directional.

The script implementations are authoritative. The option and workflow summaries
below mirror the current versions; `experiment_onoff.sh --help` prints its CLI
synopsis.

## 脚本总览

`auto_test/` 的入口、内部依赖和回归测试按下表区分。
`results/` 只存实验产物，不再放一次性执行脚本。

日常主流程：`run_all.sh` → 数据准备与 corpus 生成 → `experiment_onoff.sh` →
CSV/日志 → `gen_experiment_result.py --date YYYYMMDD` → 汇总统计、图形与论文 LaTeX。

常用命令只需：

```bash
python3 auto_test/gen_experiment_result.py --date 20260926
```

默认输出到 `auto_test/results/plots/20260926/`，无需填写输出路径。

### 日常入口与诊断工具

| 脚本 | 实际用途 | 何时使用 / 调用关系 |
|---|---|---|
| [`run_all.sh`](run_all.sh) | 编译、建库、生成 query 并运行完整工作流 | 一键入口；`--query-type join/graph/aggregate` 选择类型 |
| [`build_db.sh`](build_db.sh) | 构建或复用 Graph、TPC-H、TPC-DS、JOB 数据库 | 被 `run_all.sh` 调用，也可单独指定 family；已有数据库默认复用 |
| [`gen_outerjoin_benchmark.py`](gen_outerjoin_benchmark.py) | 生成去重 SQL、manifest、历史名称映射及三档语义过滤；`--audit-selectivity` 核验实际过滤比例 | 修改或重建 corpus 时；不运行性能查询 |
| [`qualify_benchmark.py`](qualify_benchmark.py) | 按 cpu9 实测、双方各 10 分钟超时、双侧 >1s、speed-up >=0.8 和实际 selectivity 筛选 | 输出排除原因、每 family/tier 的有效数量/缺口和统计，不修改原始结果 |
| [`gen_queries.py`](gen_queries.py) | 重建固定的 legacy SQL 来源，供当前 corpus 的 graph 查询和来源追溯使用 | `gen_outerjoin_benchmark.py` 的 `regenerate_legacy_sources()` 仍直接调用；文件名旧但并非废弃依赖 |
| [`experiment_onoff.sh`](experiment_onoff.sh) | 正常/OuterYan 的计划选择、裸查询正确性、计时和 profiling | 主实验入口；输出逐 query TXT/CSV，调用共享统计与 profiling 模块 |
| [`check_outeryan_dp.py`](check_outeryan_dp.py) | 只用只读 `EXPLAIN` 检查各生成用例是否进入 DP，并记录选择的 plan 与原因 | 优化器覆盖与选择检查；需已有数据库和编译好的 CLI；不是性能测试 |
| [`trace_outer_yan.sh`](trace_outer_yan.sh) | 记录单条 query 或失败 SQL 的优化阶段 trace | 使用 `--db DB -f QUERY.sql`；会实际执行裸查询，需显式指定数据库 |
| [`reprocess_experiment_logs.py`](reprocess_experiment_logs.py) | 从已保存 TXT/CSV 恢复逐 query 结果和统计，保留已有 CSV 精度 | 日志恢复、统计阶段失败后的重处理；不执行 SQL |
| [`gen_experiment_result.py`](gen_experiment_result.py) | 统一 CSV 合并、统计规则、Matplotlib 图形及论文 LaTeX 生成；内含 pandas/pyarrow 兼容处理 | `--date YYYYMMDD` 生成全部结果；实验 harness 和日志恢复也共用该文件的统计接口 |

### 被主流程调用的内部依赖

这些文件通常不直接运行，不能按“没有独立命令”判断为无用。

| 模块 | 实际用途 | 调用方 |
|---|---|---|
| [`configs.sh`](configs.sh) | DuckDB/数据库路径、scale、线程、超时和 corpus 的统一默认配置 | `run_all.sh`、`build_db.sh`、`experiment_onoff.sh` |
| [`benchmark_corpus.py`](benchmark_corpus.py) | 生成器、统计与复现共享的 SQL 身份、命名及历史路径解析 | 内部模块，无独立 CLI |
| [`balanced_benchmark.py`](balanced_benchmark.py) | 配平候选、完整复合连接键、固定历史排除证据、独立 reserve batch | 当前主生成入口委托该模块；不读取本机 results/ |
| [`thread_sweep.sh`](thread_sweep.sh) | 解析线程列表、拒绝非法/重复线程数 | `run_all.sh`、`experiment_onoff.sh` 通过 `source` 使用 |
| [`phase_profile.sh`](phase_profile.sh) | 每侧依次预热、profiling、正式计时；同一 ON profile 提供 optimizer 和 R1/R2/R3/Other CPU | `oy_warm_profile_time` 执行；`oy_optimizer_profile_from_files` / `oy_phase_profile_from_json` 解析 |
| [`legacy_corpus.py`](legacy_corpus.py) | 固定 legacy 成员、历史超时排除、来源与对照集合 | 两个 corpus 生成器；不依赖本机历史结果文件 |

### 回归测试（不是临时实验脚本）

| 测试 | 验证内容 |
|---|---|
| [`test_run_all.py`](test_run_all.py) | 主入口的默认版本、CLI 选择和 query 生成/运行衔接 |
| [`test_experiment_onoff.py`](test_experiment_onoff.py) | 使用模拟 DuckDB 验证 shell harness、超时、正确性、计划与 profiling 行为 |
| [`test_gen_outerjoin_benchmark.py`](test_gen_outerjoin_benchmark.py) | corpus 可重建性、成员、SQL/manifest 与不依赖历史结果文件的约束 |
| [`test_balanced_benchmark.py`](test_balanced_benchmark.py) | 720 候选配平、mixed join、复合键、reserve 去重与实测资格边界 |
| [`test_gen_experiment_result.py`](test_gen_experiment_result.py) | 统计、图形、论文表格与统一 CLI；覆盖日期默认目录、多线程隔离、1 秒边界、profile 配对和无需 Matplotlib 的 harness 汇总 |
| [`test_reprocess_experiment_logs.py`](test_reprocess_experiment_logs.py) | 日志恢复、CSV 精度、超时识别与不完整批次处理 |

运行脚本层测试（无需运行完整 benchmark）：

```bash
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/outeryan-mpl \
  python3 -m unittest discover -s auto_test -p 'test_*.py'
```

### 本次移除与保留边界

- 已删除旧 timeout SQL 档案、论文模板目录及 PostgreSQL replay/PGPlan 脚本。
  主流程统一运行 DuckDB Original/OuterYan 对比；旧 timeout 仅保留排除元数据，
  生成器不再读取已删除 SQL。论文统计和 LaTeX 仍由 `gen_experiment_result.py` 生成。
- 原统计、绘图、论文和依赖加载四个实现已合并到 `gen_experiment_result.py`，旧入口删除，
  对应测试也合并为 `test_gen_experiment_result.py`。`reprocess_experiment_logs.py` 只负责日志
  恢复，继续复用统一统计接口，不另维护结果计算逻辑。

- 删除旧 `audit_cost_gate.py` 和只测试该旧审计器的 `test_audit_cost_gate.py`：其
  normal/forced 审计强制要求 `t1_off/t1_on/t1_speedup`，不兼容当前仅输出 TM 的
  实验 CSV，也未接入当前主流程；相关旧双跑使用说明一并删除。
- 删除 `results/optimizer_cost_gate_20260928/` 下的 `collect.py`、`analyze.py`、
  `write_report.py` 和 `results/optimizer_selection_strict120_20260928/collect.py`：
  它们依赖固定日期路径及当次阈值/数字，属于一次性分析。已有 decisions、analysis、
  JSON/Markdown 报告保留为历史记录；旧报告不再提示运行已删除脚本。
- 删除 `phase_profile.sh` 内无人调用的旧 `oy_phase_profile` 及其失败占位 helper，
  保留主 harness 正在调用的单次 OFF/ON profile 与 JSON 解析实现。
- `check_outeryan_dp.py` 可复查当前 DP 覆盖和 plan selection，但不替代历史
  threshold replay 或被删除审计器的 forced-runtime 分类。
- 保留 SQL corpus、manifest、原始实验数据、论文生成器和上述测试；它们是输入、
  产物或有效依赖，不按文件数量删减。今后一次性脚本放 `/tmp`，可复用工具才加入
  本目录并更新这份清单。

### 数据与文档目录

| 目录 | 用途 |
|---|---|
| `outerjoin_benchmark/` | 720 条当前查询（Graph 172、TPC-H 176、TPC-DS 206、JOB 166）、manifest、固定筛选证据与历史档案；含 15 条 TPC-DS 三档扩展 |
| `outerjoin_query_old/` | 当前生成器仍使用的固定 legacy SQL 来源 |
| `pg_oj_trace/` | PostgreSQL 枚举空间的历史分析报告与 witness SQL，独立于已删除的 replay 工作流 |
| `results/` | 原始与重处理 CSV/TXT、profiles、统计、图和生成的论文片段 |

`trace_outer_yan.sh` 使用自己的命令行/环境默认值，不读取 `configs.sh`。

## Current configuration

Environment variables override `configs.sh`; experiment CLI options override the
corresponding environment values.

| Variable | Current source default | Meaning |
|---|---:|---|
| `PYTHON_BIN` | `python3` | Python 3.7+ interpreter; statistics require NumPy/pandas; may be an absolute repo-local path |
| `DUCKDB_BIN` | `build/release/duckdb` | Release CLI, with debug fallback if release is absent |
| `GRAPH_DATASET` | `bitcoin` | SNAP source used when `graph_db` is built |
| `TPCH_SF` | `50` | TPC-H generation scale and default database filename suffix |
| `TPCDS_SF` | `50` | TPC-DS generation scale and default database filename suffix |
| `TPCH_DB` | `tpch_${TPCH_SF}.duckdb` under the repository root | Explicit database path overrides the scale-qualified default |
| `TPCDS_DB` | `tpcds_${TPCDS_SF}.duckdb` under the repository root | Explicit database path overrides the scale-qualified default |
| `OY_THREAD_COUNTS` | `32` | One default configuration; explicit space/comma-separated sweeps also work |
| `OY_THREADS` | first configuration (`32`) | Scalar override to run only one thread count |
| `OY_TIMEOUT_SECS` | `600` | Shared default per statement (10 minutes); `0` disables it |
| `OY_DUCKDB_TIMEOUT_SECS` | `OY_TIMEOUT_SECS` | Independent OFF limit; timeout does not skip ON |
| `OY_OUTERYAN_TIMEOUT_SECS` | `OY_TIMEOUT_SECS` | Independent ON limit; timeout does not skip OFF |
| `OY_BATCH_GRACE_SECS` | `30` | External timing-batch startup/serialization grace |
| `OY_RUNS` | `5` | Median of all five unprofiled post-warmup executions per configuration; `--runs N` overrides |
| `OY_CHECK_CORRECTNESS` | `1` | Compare one bare OFF/ON result pair for every query, including fallbacks |
| `OY_PROFILE` | `1` | One post-warm-up OFF/ON execution profile for optimizer totals; the same ON sample supplies phase breakdown when OuterYan is selected |
| `OY_CAPTURE_PLANS` | `0` | Save OFF/ON EXPLAIN, optimizer trace, and cost-step artifacts |
| `OY_CORPUS` | `auto_test/outerjoin_benchmark/benchmark` | Deduplicated corpus root |
| `OY_CORPUS_SCOPE` | `benchmark` | Subset: `benchmark`, `job-regressions`, or `selectivity-stress` |
| `DUCKDB_OY_FORCE_CANDIDATE` | unset | Set to `1` only to force a valid OuterYan candidate for correctness validation |

Always inspect `configs.sh` before a server run because these experiment defaults
are intentionally adjusted for the current machine.

### Frozen TPC-H setting (2026-10-13)

The active `outerjoin_benchmark/benchmark/tpch/` adopts exactly 20 reviewed SQL
replacements: all 14 predicate-only candidates, plus the complete low/medium/high
groups for Q5 bushy and Q5 right-deep. The other 11 tuning candidates are not
adopted. Counts remain 720 total / 176 TPC-H SQL instances; the current composite
measurement cohort contains 281 complete OuterYan-selected pairs / 80 TPC-H.
`sources/tpch_tuning_promotion_20261013.json` pins the exact setting and discloses
its post-hoc, performance-conditioned selection. This is a workload change, not
an optimizer implementation improvement. The generator always reproduces the
pinned SQL and never reads timing results or searches for a target speed-up.

The retained measurement snapshot uses CPU9 run `20261013_000640_t32` only for
the 20 changed SQLs and `20261010_150834_t32` for every other instance. Its overall
geometric mean is 1.8485904902x, not a guarantee or acceptance criterion for
future runs. Timing remains median-of-five, SF50 / 32 threads, 600 seconds per
execution on each engine; either-side timeouts and unmeasured fallback defaults
are excluded. A future complete run must replace this composite as a whole.

Old SQL is recoverable under
`outerjoin_benchmark/revisions/replaced_tpch_tuning_20261013/benchmark/`.
Validate the fixed setting with:

```bash
python3 auto_test/tpch_tuning_promotion.py --validate
```

After synchronizing this revision to CPU9, the normal `run_all.sh` /
`experiment_onoff.sh` commands use the fixed setting. The isolated
`run_tpch_tuning_retest.sh` remains a historical **31-candidate** pilot; do not
use it to run the promoted 20-query setting. No new run starts automatically.

To explicitly start a new complete SF50 run after pulling this revision:

```bash
env TPCH_SF=50 TPCDS_SF=50 bash auto_test/run_all.sh \
  --all --threads 32 --runs 5 --timeout 600 --no-check-correctness
```

This builds the release binary, prepares/reuses the databases, regenerates all
720 queries, and measures them. The last flag follows the current performance
protocol; omit it to enable complete result-equivalence comparisons. Existing
database path overrides must point to the requested scale. Every individual
execution has its own timeout, including each of the five timed executions.

## Build

For all four families, build a release CLI with the TPC-H and TPC-DS generators:

```bash
BUILD_TPCH=1 BUILD_TPCDS=1 GEN=ninja make release
```

`build_db.sh` can also detect missing `dbgen`/`dsdgen` support and rebuild the
release binary when needed.

## Databases

```text
bash auto_test/build_db.sh [graph|tpch|tpcds|job|all ...]
```

| Database | Source |
|---|---|
| `graph_db` | One SNAP edge list copied into R1..R10, plus R/S/T/K views |
| `tpch_<SF>.duckdb` | `CALL dbgen(sf=TPCH_SF)`; default `tpch_50.duckdb` |
| `tpcds_<SF>.duckdb` | `CALL dsdgen(sf=TPCDS_SF)`; default `tpcds_50.duckdb` |
| `job_db` | 21 JOB/IMDb Parquet files cached under `job_data/`, then loaded locally |

TPC database defaults include the requested scale. SF50 and SF100 can coexist as
`tpch_50.duckdb`, `tpch_100.duckdb`, `tpcds_50.duckdb`, and `tpcds_100.duckdb`.
Existing files are reused. An explicit `TPCH_DB`/`TPCDS_DB` takes precedence, so
changing only its corresponding SF does **not** resize that file. The Python
selectivity-audit and qualification helpers use the same defaults.
The historical design-bootstrap/legacy-query utilities and standalone paper
examples are not normal experiment entry points; supply their database paths
explicitly when supported, or export the paths from `configs.sh` first for the
design-bootstrap utility. The frozen balanced-generator provenance is preserved.

默认仍为 **TPC-H SF50 / TPC-DS SF50**。在 cpu9 上先进入 Bash（tcsh 不支持 `export`），
然后选择 scale；不会删除另一种规模的数据：

```bash
bash
cd /home/data/bchenba/DuckYanOuter
unset FORCE TPCH_DB TPCDS_DB
export TPCH_SF=100 TPCDS_SF=100
bash auto_test/run_all.sh --all --threads 32 --runs 1 --timeout 600 --check-correctness

# Later, switch to SF50 (only missing database files will be generated).
unset TPCH_DB TPCDS_DB
export TPCH_SF=50 TPCDS_SF=50
bash auto_test/run_all.sh --all --threads 32 --runs 1 --timeout 600 --check-correctness
```

脚本**不自动重命名旧库**：`tpch_db`、`tpcds_db` 和旧的 `*_sf100.duckdb` 都会保留，
但不再自动选用。已有库的真实 scale 必须根据生成记录或已核验的行数确认，不能根据
文件大小、名字或当前 `*_SF` 环境变量推断。确认后可继续显式设置 `TPCH_DB/TPCDS_DB`
复用原路径；若要统一命名，先停止所有使用它的进程，用同版本 CLI 完成 `CHECKPOINT`
并退出，再将已确认的库改名到相应的 `<family>_<SF>.duckdb`，不得覆盖已有目标，
也不能丢弃尚有内容的 `.wal`。切换 scale 时清除旧的 `*_DB` 覆盖，或同步更换路径。

`FORCE=1` 仍会删除并重建**选中的**数据库及其 WAL，不要用它进行普通的 scale 切换，
更不要使用 `FORCE=1 bash auto_test/run_all.sh` 重建所有 family。
原始 SF50/SF100 结果分别保留，不能当成同一次实验混合。
换库后重新执行 selectivity audit 和计划选择审计；此前本地计划选择数不代表 cpu9 的 SF50 结果。
当前默认 DuckDB/OFF 和 OuterYan/ON **各 600 秒（10 分钟）/statement**，独立计时；
只停止超时的一侧，不自动延长或重试，另一侧继续执行。
`--timeout 600` 设置双方；`--duckdb-timeout` / `--outeryan-timeout` 分别覆盖它，
且具体侧的 CLI 参数优先于共同参数。旧 timeout 环境值仍会覆盖默认值。
本次不修改代价模型；Graph 的 relation 数配额已调整（见下文）。

```bash
# Small TPC databases, without replacing SF50/SF100 files
env -u TPCH_DB TPCH_SF=1 bash auto_test/build_db.sh tpch
env -u TPCDS_DB TPCDS_SF=1 bash auto_test/build_db.sh tpcds

# Replace graph_db with the wiki graph
FORCE=1 GRAPH_DATASET=wiki bash auto_test/build_db.sh graph
```

JOB has no scale factor. Missing Parquet files are downloaded with `curl`; cached
files are reused. `FORCE=1` rebuilds `job_db` from that cache rather than forcing a
second download.

When `experiment_onoff.sh --only graph` is used, `graph_db` is reused by default.
Set `OY_FORCE_GRAPH_REBUILD=1` only when replacing it is intentional.

### Mixed Graph datasets and the 16-query Epinions retest

The frozen `sources/graph_dataset_retest_20261010.json` cohort consists of the
16 active Graph queries whose Bitcoin OFF and ON five-run medians were both
at most 0.1 seconds in `20261008_201332_t32`. It is selected by absolute runtime,
not speed-up. After the completed CPU9 retest, one grouped-count replacement
(star4/converging, left-deep, low) was retired at user request after predicate
review. The other 15 remain active, including 12 timeout outcomes and one fallback.
Three more short queries (previous IDs G-G-RD-05, G-G-B-12 and G-G-B-09, both
Bitcoin medians below 0.2 seconds) were moved to Epinions. Their policy is frozen in
`sources/graph_dataset_extension_20261010.json`, with calibrated SQL in
`graph_dataset_retest/epinions_extension/`. The Graph family now contains
156 Bitcoin and 16 active Epinions queries, 172 instances in total.
On 20261011, the two low/bushy chain4 instances (`ifl/2bb39801`, `lfr/1170f7ed`)
were retired after CPU8 OuterYan timeouts in profile/kernel, respectively.
Exact SQL identities and evidence are pinned in
`sources/graph_timeout_retirements_20261011.json`; historical SQL is retained
in the frozen extension directory. These are outcome-conditioned removals,
not an optimizer improvement. Normal generation and execution exclude them,
without removing their Bitcoin medium/high variants or mixing CPU8 timings into CPU9 statistics.
Other families are unchanged. No old Bitcoin timing is retained for a replaced query.

The manifest's `graph_dataset` column routes each query: Bitcoin uses `GRAPH_DB`
(default `graph_db`), Epinions uses `GRAPH_EPINIONS_DB` (default
`graph_epinions.duckdb`). `experiment_onoff.sh` builds the Epinions database if
needed without rebuilding Bitcoin. The mixed active corpus requires
`GRAPH_DATASET=bitcoin`; do not globally change it to Epinions. Both `run_all.sh`
and direct harness runs honor this per-query routing. Normal regeneration
reapplies the pinned replacement; original SQL is recoverable under
`outerjoin_benchmark/revisions/replaced_graph_bitcoin_20261010/benchmark/`.

```bash
# Prepare/calibrate only; do not execute the performance workload.
bash auto_test/run_graph_dataset_retest.sh --prepare-only

# Historical 16-query retest (includes the subsequently retired query).
# For the current active corpus, use run_all.sh --all instead.
bash auto_test/run_graph_dataset_retest.sh --run
```

This creates/reuses **`graph_epinions.duckdb`**, never overwrites the Bitcoin
database, and runs the separate corpus
`outerjoin_benchmark/graph_dataset_retest/epinions/`. `GRAPH_EPINIONS_DB` can
override that file but must not point at the Bitcoin database. Epinions has
508,837 edges in the cached SNAP source, versus Bitcoin's 24,186. Larger input
does not guarantee either a longer runtime or completion below the timeout.

The generator calibrates source-ID cutoffs from base-table counts, before
timing. It preserves each query's mixed join types, join expression, projection,
aggregation, and selectivity band: anchor targets remain 3%/30%, and auxiliary
input targets remain 9%/15%. It audits R1..R5 separately. Dataset-qualified query
IDs, a manifest, a query list and `dataset_audit.json` distinguish these new
measurements from the old Bitcoin results. They replace, rather than add to,
the original 16 instances and must never inherit the old timings.

The retest uses **32 threads, five timed executions per side and their median**,
with an independent **600-second limit on each execution**, not on all five
combined. Warm-up and profiling precede timing. Full result-multiset comparison
is disabled for this performance retest, matching the latest full run; the
local small-data check is not a full Epinions correctness certification. Plans,
profiles and results use the existing `auto_test/results/` output convention.
The wrapper does not compile, commit, push, or promote candidates into the
active corpus automatically.

## Query corpus

主查询集 `outerjoin_benchmark/benchmark/` 默认运行 **720 条唯一候选 SQL**：
Graph 172、TPC-H 176、TPC-DS 206、JOB 166。
基础设计原为每 family 180 条，每档每 shape 各 20；经性能筛选后不再严格配平。
join kind 仍为 mixed。Graph 的 4/5 relation 数量分别为 **121/51**，不再生成 6 relation 查询。
基础单元为 14/6；筛选后 low/left-deep 为 12/5，low/right-deep 为 14/4，
low/bushy 为 11/6，其余单元不变；156 条使用 Bitcoin，16 条使用 Epinions。
Graph 查询名带 `__inputcap1__`，不能将旧 SQL 的时间混入新结果。
Bitcoin 的 R1 保持三档 `src <= 2/83/306`；R2…Rn 分别增加 `src <= 10/20/40` 的输入谓词，
放在 `(SELECT src,dst FROM Ri WHERE ...) Ri` 中，避免在根 WHERE 误删 NULL-padded 行。
本地 Bitcoin 的 R1 保留率为 2.83%/30.00%/54.99%；其余每个输入约为
9.33%/14.35%/21.19%。三档配平指 **R1 主过滤**，不能宣称所有输入过滤率均匀分布，
也不能将各输入的边际比例相乘当作 join selectivity。
`manifest.csv` 的 `input_filter_profiles_json` 记录逐关系谓词及本地校准比例；
每次实验保存对应的 `.manifest.csv` 快照。cpu9 的 selectivity audit 会检查每个参与输入，
资格筛选要求主过滤和所有输入 caps 均已验证。更小的输入仍可能产生大中间结果，
也可能使查询小于 1 秒；只有 cpu9 实测后才能确定有效数，不能保证 180 条全部合格。
类型为 `join` 375、`graph` 162（含 industry controls）、`aggregate` 183。
`--only graph` 选择 Graph family 全部 172 条，与 `--query-type graph` 不同。
原版本已合并；**候选数不是最终有效实测数**，fallback 和 timeout 不能算作完整实测配对。

20261009 按用户要求精确移出 Graph star5/converging、right-deep、low 的 global COUNT 查询
（5 次中位数：DuckDB 8.52 ms、OuterYan 17.44 ms）。medium/high 不变，不按新的通用阈值删减。
固定清单为 `sources/retirements_20261009.json`，可恢复 SQL 在
`outerjoin_benchmark/revisions/retired_queries_20261009/`；重新生成和默认执行均不会恢复此查询。

20261005 的 TPC-DS 调整按 20261002 实测移出 28 条 timeout、8 条 speed-up <0.5 的 SQL，
保留 147 条，并加入 18 组历史表达式 × 三档 = 54 条候选，总计 201 条。
Q80-alt/Q80-left-deep/Q93-left-deep 三条旧非聚合补充也因 timeout 移出。
36 条原 SQL 可在 `outerjoin_benchmark/revisions/retired_tpcds_20261005/benchmark/` 恢复；原始 CSV 不改。
生成器读取固定 `sources/tpcds_refresh_20261005.json`，不会在下次 `run_all.sh` 恢复已剔除 SQL。

同一批实测共有 13 条 speed-up <0.5，其中 8 条 TPC-DS 已移出。
全 benchmark 筛选另外移出 Graph 1、TPC-H 1、JOB 3，故总数从 741 降至 736。
仅排除确切 SQL，保留同表达式其它档位；0.5 本身保留，不额外剔除 timeout/fallback。
这次筛选证据原固定在 `sources/speedup_screen_20261005.json`；
5 条原 SQL 和 manifest 归档到 `revisions/retired_speedup_20261005/benchmark/`，原始结果 CSV 不改。

20261005_201226_t32 的新 TPC-DS 批次已在 cpu9 测完：201 条均通过等价性检查，
43 条有完整实测配对，158 条 fallback-skip，无 TPC-DS timeout。
20261007 再按该批次实测移出 7 条 speed-up <0.5 的查询（6 条 aggregate、1 条 join），
该次筛选后 TPC-DS 为 194 条，其中 36 条有完整配对、158 条 fallback-skip；原 54 条恢复候选保留 47 条。
因此约 50 条完整实测的目标尚未达到，不能把 fallback 默认 1× 当成实测。
累计 12 条额外 speed-up 剔除（旧 5 条 + 新 7 条）的固定证据为
`sources/speedup_screen_20261007.json`，清单为 `benchmark/speedup_excluded.csv`。
新移出的 7 条 SQL 和 manifest 可从 `revisions/retired_speedup_20261007/benchmark/` 恢复；
旧档案与所有原始结果不变，常规重新生成也不会恢复这些确切 SQL。
本次不额外移出其它 timeout/fallback，也不修改其余档位的 SQL。

20261008 按 `experiment_onoff_benchmark_20261007_161108_t32.csv` 的完整实测，
再从当前 benchmark 移出 **2 条 Graph 和 9 条 JOB 的 speed-up <=0.7 查询**。
只移出确切 SQL；TPC-H/TPC-DS 不变，不连带删除其它档位或 timeout/fallback。
这 11 条均为双方 <1s 的单次计时，且本轮为 `NOT-CHECKED`，不将其冒充验证过的慢查询。
新增固定证据为 `sources/speedup_screen_20261008.json`；SQL 可从
`revisions/retired_speedup_20261008/benchmark/` 恢复。
重新生成会重放固定排除清单，因此 `run_all.sh --all` 和 `experiment_onoff.sh --all`
均不会恢复这 11 条；该次移出后为 718 条，不会根据未来的 CSV 自动追加新的筛选。
同一次原始测量在新 manifest 上有 242 条有效 OuterYan-selected 配对。
论文须披露这一基于实测结果的筛选，不能把删减后加速比的增加描述成优化器性能提升。

随后增加的 15 条 TPC-DS 扩展采用当前 low/medium/high 三档。
初版 SQLStorm 11376 的 bushy 三档在 SF50 双侧超时；r2 将两个 11376 结构的
6 条候选移入归档，换成 SQLStorm 14368 的单事实表 4/5 表 connected-subgraph。
其余 9 条 SQL 不变，扩展现为 9 bushy、3 left-deep、3 right-deep，均非聚合。
新结构没有可复用的历史速度比；所有候选须重新测试，不以目标几何平均选择。
现在共 720 条，TPC-DS 206 条，其中 45 条有有效配对实测；约 50 条有效配对是目标而非保证。
只编译并复测这 15 条（复用数据库，关闭完整正确性比较）：

```bash
env SKIP_DATA=1 TPCDS_SF=50 OY_RUNS=1 OY_PROFILE=1 OY_CHECK_CORRECTNESS=0 \
  bash auto_test/run_all.sh --all --threads 32 --timeout 600 \
  --query-list auto_test/outerjoin_benchmark/benchmark/tpcds_extension.txt
```

不能把旧速度比当成新查询结果。恢复组保留旧 join expression 与过滤 relation，
旧取模模式采用约 3%/30%/55% 的 identifier buckets，Q93/control 保留语义谓词。
它们明确标为性能筛选的历史扩展，不宣称业务语义过滤或无偏采样。
Q5/Q40/Q80 大输出模式采用明确命名的 COUNT 变体，仍由两侧执行同一裸查询。
恢复组最初每组包含三档；确切 SQL 筛选后，部分表达式不再三档齐全，
不因一个档位表现差而默认排除整个表达式。

只重测 TPC-DS（含编译/重新生成），或仅测新增候选（使用现有编译）：

```bash
bash auto_test/run_all.sh --only tpcds --timeout 600 --check-correctness
bash auto_test/experiment_onoff.sh --all --timeout 600 --check-correctness \
  --query-list auto_test/outerjoin_benchmark/benchmark/tpcds_recovery.txt
```

默认双方各 10 分钟测试可用 `bash auto_test/run_all.sh --all`。
默认及配平资格政策均为双方各 600 秒；旧 900/1800 秒结果保留原记录，不混作新的资格测量。
默认检查所有 query 的等价性。任何一侧超时都不阻止另一侧执行；若等价性阶段超时，
`correct=TIMEOUT`，仍保留完成侧的时间/profile，精确 speed-up 为 `NA`，不混入有效配对统计。

查询名包含类型、执行 benchmark、来源/结构、join vector 和 selectivity 档位，例如
`join__tpch__q05_region_sales_ldmx__ilrf__sel_low`（新名称还带 expression hash）。
主过滤档位为 `(0,5%)`、`[5,40%)`、`[40,60%]`。基础组件使用语义谓词，恢复组件的 identifier buckets 单独标明。
基础组件保留完整复合连接键；历史恢复组件保留归档键，部分为 item-only；Graph/industry controls 明确记录 synthetic 来源。
基础组件排除历史 speed-up <0.8 或确认 30 分钟超时的表达式；恢复组件仅根据明确的新 SQL 变体重新评估，且防止已知失败 SQL 仅换名后加入。
这是 **historically/performance-screened** 集合，论文不能描述成无性能筛选的随机样本。

```bash
python3 auto_test/gen_outerjoin_benchmark.py
bash auto_test/experiment_onoff.sh
bash auto_test/experiment_onoff.sh --query-type join --only tpch
bash auto_test/experiment_onoff.sh --query-type aggregate
python3 auto_test/check_outeryan_dp.py --out auto_test/results/unique_optimizer_audit_sj020.json
python3 auto_test/gen_outerjoin_benchmark.py --audit-selectivity --audit-timeout 600
```

`--version` 已移除；`--all` 等同默认唯一查询集。
去重身份保留 execution family、字符串常量、join 类型与括号结构，忽略注释和格式。
旧 650 条 SQL 和名称映射保存在 `revisions/unique_semantic_20260929/benchmark/`，
旧结果 CSV 不修改。候选三档成组配对；旧 stress/regression scope 不用于新集合。详细规则见
[benchmark README](outerjoin_benchmark/README.md)。

### 本地修改与 cpu9 重测

流程：本地修改/验证 → commit & push origin → cpu9 `git pull --ff-only`。
不直接修改 cpu9，也不以本地 SF1 时间代替服务器结果。cpu9 上：

```bash
cd /home/data/bchenba/DuckYanOuter
git pull --ff-only
bash auto_test/run_all.sh --all --timeout 600
python3 auto_test/gen_outerjoin_benchmark.py --audit-selectivity --audit-timeout 600 \
  --audit-output auto_test/results/cpu9_selectivity_audit.json
python3 auto_test/qualify_benchmark.py \
  --selectivity-audit auto_test/results/cpu9_selectivity_audit.json \
  --results auto_test/results/experiment_onoff_benchmark_TIMESTAMP_t32.csv \
  --output-dir auto_test/results/qualified_TIMESTAMP
```

`TIMESTAMP` 换成实际文件时间。`run_all.sh` 包含编译；`experiment_onoff.sh` 不编译。
实际数据库路径不同可设置 `GRAPH_DB/TPCH_DB/TPCDS_DB/JOB_DB`，audit 和实验必须一致。
CSV 新增 timeout、执行 host、SQL/manifest hash、数据库签名，旁边保存 `.manifest.csv` 快照。
`qualified_TIMESTAMP/qualification.csv` 查看每条去留原因；`coverage.csv` 查看每档缺口；
`qualification_summary.json` 查看各 benchmark geomean/min/max/median/std。
资格门槛读取 manifest：当前主查询集所有 family 都要求 speed-up >=0.5；TPC-DS 时间 >0，其它 family 仍为双侧 >1s，双方均 <600s。
这不改变亚秒结果的 review 统计口径；旧版/备用 batch 保持其 manifest 中的门槛。
正确性通过或显式关闭检查（后者不能宣称已验证），fallback-skip 不算有效测量。
`qualify_benchmark.py` 的默认 180/family 配平目标是旧资格流程，不等于本次约 50 条 TPC-DS 完整配对的探索目标。
缺额必须补候选并重测，不能补成默认 1×。完整结果与筛选后结果分别保留。

## Experiment pipeline

`experiment_onoff.sh` and `run_all.sh` use **32 threads only** by default.
Request a sequential sweep explicitly with `--threads "16 32"` or
`OY_THREAD_COUNTS="16 32"`; each configuration uses separate processes and
output files. Use `--threads 16` / `OY_THREADS=16` for a different single
configuration. Thread counts must be greater than one; CLI settings take
precedence. Database setup and query generation in `run_all.sh` happen only
once before any requested sweep.

For every corpus query included in the run at each thread count, `experiment_onoff.sh` performs:

1. Read a traced `EXPLAIN` decision. Only a verified `DUCKDB:0` plan decision
   skips performance measurements, while still undergoing the default correctness
   check. An OuterYan-selected aggregate query is measured even without aggregate
   pushdown: its join/SJ tree can still differ from DuckDB's native plan.
2. **Correctness comparison is on by default for every query.** Run the bare
   query once OFF and once ON and compare their complete result multisets.
   A mismatch/error stops that query before profiling or timing. Both correctness
   executions are attempted independently. A timeout stops only that side;
   the completed side can proceed, with equivalence unverified and speed-up `NA`.
   A verified fallback records `correct=TRUE`, `timing_status=fallback-skip`,
   no measured runtimes, and policy-default speed-up 1.0 excluded from statistics.
   A failed fallback records the actual failure, never a default 1.0 speed-up.
   Explicit `--no-check-correctness` remains available for diagnostics; unchecked
   measured rows are `NOT-CHECKED`, not verified correct.
3. Keep the existing one-shot ON kernel diagnostic (bitmap/hash classification);
   it does not supply a runtime sample or warm the later connection's buffer pool.
4. Start a fresh CLI for **each** of OFF and ON. In that same process execute:
   **one unprofiled warm-up → one detailed profile → disable profiling → five
   unprofiled timed executions**. Both preparatory executions are excluded from
   runtime. Report the median of all five timed samples independently for OFF
   and ON; speed-up is median(OFF) / median(ON), not the median of paired ratios.
   Explicit `--runs N` accepts a positive odd N; `--runs 1` uses a single sample.
5. Read optimizer totals and workflow phases from the already-produced profiles;
   read R1/R2/R3 and Other CPU work from that same ON profile. No further query
   execution is needed. OFF uses DuckDB's `all_optimizers`; ON additionally
   includes the otherwise-untracked cost-model phase. Generic optimizer-pass
   timings are not substituted for the named OuterYan workflow phases.

With default correctness and profiling enabled, a fully completed selected query
executes **17** times: two correctness checks, one kernel diagnostic, and seven
executions per configuration. A verified fallback executes only the two checks.
Only ten executions (five OFF and five ON) contribute to runtime/speed-up.
With `--no-check-correctness`, there are 15 executions including the kernel
diagnostic. `--no-profile` keeps one warm-up + five timed executions per configuration.
The compact profiling trace is emitted only while the native profiler is enabled;
it does not write during formal timing. **Rebuild the binary** for this behavior:
use `run_all.sh`, not a stale CLI with `experiment_onoff.sh`.

Each engine has an independent 600-second default per statement. The process watchdog
covers `(1 + profile + runs) * limit + grace`, not a larger per-query allowance.
The first timeout stops only the affected engine, with no retry. A profiling
timeout occurs *before* timing, so that engine cannot yield a measured runtime.
The other engine still runs; its runtime and profile remain available. CSV/TXT
record `duckdb_status` / `outeryan_status`, their `*_timeout_seconds`,
`*_timeout_stage`, and `*_correctness_status`. Partial optimizer profiles have
status `PARTIAL`, unavailable totals/overhead are `NA`, and censored pairs do not
contribute to exact speed-up statistics. If only later timing times out, a
completed correctness check remains `TRUE`. `statistics.json` additionally reports
per-engine timeout counts by stage and workload family.
If executions finish but profile JSON validation fails, retain the independently
valid unprofiled timing pair and report the missing diagnostic as an error.

All executions use the selected multi-thread count. Timing uses `.mode trash`
to fully drain the **bare query**, without wrappers or result-file formatting.
Only the correctness checks export/sort results; these checks are not runtime
samples. Logs/CSV carry `correctness_check`, `timing_protocol`, `timing_samples`,
`timing_estimator`, and `warmup_runs_per_side` (including the profiling warm-up).
Statistics accept explicit unchecked measured rows, preserve their status, and
report their count; generated paper text must not call them correctness-verified.
Do not pool historical single-sample or three-run results with the new five-run
medians as one measurement configuration; qualification rejects mixed protocols.

**Where to change the sample count:** `configs.sh`, section 6, sets
`export OY_RUNS="${OY_RUNS:-5}"`. `experiment_onoff.sh` reads that value and applies
any `--runs N` override. `phase_profile.sh::oy_warm_profile_time` executes the
timing loop and calls `statistics.median(values)` only if all N samples completed
successfully. A timeout never produces a median from the remaining samples.
The precedence is **CLI `--runs` > environment `OY_RUNS` > default 5**.

Full SF50 performance rerun, reusing existing databases and omitting correctness
comparison (compilation and query generation still run):

```bash
env SKIP_DATA=1 TPCH_SF=50 TPCDS_SF=50 \
  bash auto_test/run_all.sh --all --threads 32 --runs 5 --timeout 600 \
  --profile --no-check-correctness --capture-plans
```

`--timeout 600` applies to **each statement on each engine**, including every
timed execution; it is not a 10-minute total budget for all five executions.
DuckDB and OuterYan stop independently on their first timeout, without retrying.

The read-only diagnostic [`graph_count_annotation_check.sql`](diagnostics/graph_count_annotation_check.sql)
reproduces the count-weight arithmetic behind the previously incorrect `graph_branch5_forward`
`bushy/rlfi/global_count` mismatch without materializing its large join result.
The optimizer fix normalizes each COUNT multiplicity before multiplication:
`COALESCE(left_annot,1) * COALESCE(right_annot,1)`, rather than repairing only the
final product. It adds no row filters and does not change SUM/MIN/MAX NULL semantics.
The diagnostic still reproduces the old arithmetic for comparison; it is not a
substitute for bare-query equivalence.

Bare-query equivalence can require temporary space comparable to several query
result sets. Temporary result and external-sort files default to
`<repo>/auto_test/results/tmp`. At
`/home/data/bchenba/DuckYanOuter`, this resolves to
`/home/data/bchenba/DuckYanOuter/auto_test/results/tmp` on the large `/home`
filesystem. The harness prints the resolved path and free capacity at run
start. Each experiment uses a separate `run_<timestamp>.*` subdirectory that
is removed on normal exit and Ctrl+C. Override `OY_TMPDIR` only when another
filesystem is preferred. A DuckDB or sort write failure is reported as
`ERROR` with its concrete stderr and is never classified as `NOT-EQUIV`.

### Plan decision and cost gate

For an applicable query, OuterYan constructs its DP/OJT candidate and DuckDB's
normal outer-join-simplified, join-ordered baseline from the same input plan.
Grouping comparison uses stable base-table identities and ignores join type,
child orientation, and inserted semi-join wrappers.

Generated modulo and hash predicates participate in the cardinality estimates
used by DP, including predicates pushed into scans. `x % k = 0` uses `1/k`;
`hash(x) % k` comparisons use the fraction of matching residue buckets. Scan
filters and residual filters share this estimator, and NDVs are capped at the
filtered row estimate. These are uniform-distribution heuristics, so they do
not qualify for relaxed confidence gates. Intermediate predicates move only
after proving NULL rejection; a hash expression is evaluated with typed NULL
inputs rather than assumed to propagate NULL. Queries that simplify to an
all-INNER acyclic skeleton still enter OuterYan DP.

Check DP coverage of all generated suites (including JOB regressions) without
executing their joins:

```bash
python3 auto_test/check_outeryan_dp.py --out auto_test/results/dp_coverage.json
```

The check uses the release binary and existing `graph_db`, `tpch_<SF>.duckdb`,
`tpcds_<SF>.duckdb`, and `job_db`; `DUCKDB_BIN` and the corresponding `*_DB` variables
override them. It fails on planning errors or queries that do not complete
DP. This is a planning check, not a correctness or performance benchmark.
Aggregate pushdown is separately skipped when retained post-join filters or
aggregate arguments reused as join/group keys still require raw input values;
the selected join/SJ plan remains available.

A same-grouping candidate always selects DuckDB. For a changed grouping, the
source-level gate computes:

```text
semijoin_raw_cost = round1_build + round1_probe + round2_build + round2_probe
weighted_semijoin_cost = SEMIJOIN_COST_RATIO * semijoin_raw_cost
candidate_total = candidate_join_cost + weighted_semijoin_cost
strict_ratio_limit = LOW_RETENTION_MAX_CANDIDATE_TO_BASELINE_RATIO
                     when semijoin_retained_cardinality_ratio < 0.90,
                     otherwise MAX_CANDIDATE_TO_BASELINE_RATIO
if aggregate_query:
    strict_ratio_limit = min(strict_ratio_limit, AGGREGATE_MAX_CANDIDATE_TO_BASELINE_RATIO)
strict_threshold = strict_ratio_limit * baseline_cost

select OuterYan on the strict tier iff candidate_total <= strict_threshold
```

Cost formula V9 retains two consistency checks before that final comparison.
For fully reduced all-INNER candidates, every intermediate estimate is bounded
below by the largest reduced leaf in its subtree. For table filters that used
DuckDB's generic selectivity fallback, the candidate and baseline are also
scored with unfiltered base cardinalities; the gate uses whichever scenario
has the higher candidate/baseline ratio. These checks target false-positive
selections in the slow tail independently of the configured ratio limits.

The uncertain-filter amplification guard also rejects a candidate when the
largest input is at least `1000x` the uncertain filtered relation and the two
reducer rounds retain at least `99%` of estimated input cardinality. The trace
records the retention ratio, amplification, and guard result explicitly.

The current experimental V9 configuration uses `0.20 * semijoin_raw_cost` and
a confidence-aware stretch tier without changing DP enumeration. The prior
conservative configuration used `1.0`; report these configurations separately.
The experimental weight is not a calibrated runtime coefficient. The current normal, low-retention, and aggregate strict
limits are all `1.20`: a changed candidate may cost up to `20%` more than the
baseline in the limiting estimation scenario. The low-retention knob applies
when reducer rounds retain less than `90%` of estimated input rows; it remains
separate so future experiments can require additional headroom in that regime.

The stretch ceiling is also `1.20`, so it currently adds no allowance beyond
the strict gate. Its eligibility checks remain available for diagnostics and
experiments that lower the strict limits:

```text
not a root aggregation/DISTINCT query
no heuristic modulo/hash selectivity estimate
no generic/default-filter upper-bound scenario
no uncertain-filter amplification guard
no active full-reduction cardinality lower-bound correction
candidate_join_cost < baseline_cost
candidate_join_input_rows <= 0.30 * baseline_join_input_rows
semijoin_retained_cardinality_ratio >= 0.95
```

`candidate_join_input_rows` and `baseline_join_input_rows` sum the left and
right cardinalities processed by every real join, approximating hash
build/probe work that the output-only join cost does not capture. An eligible
candidate admitted only by this tier is selected with reason
`COST_OUTERYAN_STRETCH`; with the current equal ceilings, no candidate needs it.
These constants are experimental safety margins, not a runtime performance
guarantee.

V9 also exposes a separate stats-backed unary-filter tier. Let `s` be the
minimum filtered/base cardinality ratio among pre-join base scans. A predicate
retained at root scope is not credited because it does not reduce join or
semi-join inputs. If `s <= 0.35`,
the estimate is neither a modulo/hash heuristic nor DuckDB's generic filter fallback, the confidence
guards above are clear, `candidate_join_cost < baseline_cost`, and the
candidate/baseline join-input ratio is at most `0.75`, the gate computes:

```text
progress = (0.35 - s) / 0.35
low_selectivity_limit = strict_ratio_limit
                        + progress * (1.20 - strict_ratio_limit)
```

The final relaxed limit is the maximum applicable tier. When the strict limit
is below `1.20`, this formula continuously increases the allowance as selectivity
decreases. With all strict limits at `1.20`, the formula stays at `1.20` for
every selectivity. Generic/default 20% estimates never qualify. A nonaggregate
candidate admitted only by this tier records `COST_OUTERYAN_LOW_SELECTIVITY`.

The trace and CSV report two separate comparisons: `raw_cost_winner` compares
`candidate_total` directly with `baseline_cost`, while `gate_result` compares
`candidate_total` with `baseline_threshold`. `selected_plan` is the plan that
is actually returned and can differ because of same-grouping or proven-empty
policy decisions.

The policy knobs are `constexpr` members of `OuterYanOptimizer` in
`src/include/duckdb/optimizer/outer_yan/pipeline/outer_yan_optimizer.hpp`; they
are not environment variables or SQL settings. The current workspace selects
`GATED`, uses the experimental semi-join ratio `0.20`, and sets the normal, lower-retention,
and aggregate strict limits to `1.20`. Both confidence-gated ceilings remain
`1.20`, so no tier admits a cost above `1.20 * baseline_cost`.
Rebuild the CLI after changing these source-level settings.

Set `SELECTION_MODE` to `SelectionMode::GATED` for the cost gate, or to
`SelectionMode::FORCE_OUTERYAN` to select every complete,
changed-grouping, non-proven-empty OuterYan candidate. Same-grouping,
inapplicable, failed, and proven-empty cases continue to use DuckDB in both
modes. The selected mode is written to `[OY_DECISION]`, TXT, and CSV output.

#### Force a same-grouping or cost-rejected candidate

The source-level `FORCE_OUTERYAN` mode still preserves the same-grouping
shortcut. Therefore `correct=TRUE selected=DUCKDB` does not validate the
OuterYan candidate. For a targeted correctness run, use the command-scoped
diagnostic override:

```bash
DUCKDB_OY_FORCE_CANDIDATE=1 \
bash auto_test/experiment_onoff.sh \
  --only tpcds \
  --query-type join --limit 1 \
  --check-correctness --runs 1 \
  --capture-plans
```

The harness's OFF processes continue to use
`SET disabled_optimizers TO 'outer_yan';`. Its ON processes execute the
OuterYan candidate even if `outer_reordered=0` or `raw_cost_winner=DUCKDB`.
This override bypasses grouping equality and the cost gate only after the
candidate is known to be complete and the DuckDB baseline is not proven empty.
Aggregate/DISTINCT, inapplicable, failed, and proven-empty cases remain on
DuckDB.

A successful validation must report:

```text
correct=TRUE ... selected=OUTERYAN ...
decision=[mode=FORCE_OUTERYAN_DIAGNOSTIC
          reason=FORCE_OUTERYAN_DIAGNOSTIC
          ... gate=SKIPPED ... outer_yan_selected=1 ...]
```

`reorder=0` means that the two candidates have the same base-relation grouping;
it does not contradict `selected=OUTERYAN`. Use `kernel=bitmap(...)`,
`kernel=hash(...)`, `kernel=mixed(...)`, or `kernel=none(...)`, plus the saved
enabled plan and trace, to inspect the executed semi-join candidate. Keep the
variable command-scoped so later experiments return to the configured
`GATED`/`FORCE_OUTERYAN` policy automatically.

Decision reasons written to the trace and result files include:

| Reason | Meaning |
|---|---|
| `INAPPLICABLE` | OuterYan applicability check failed |
| `DUCKDB_PLAN` | Candidate has the same grouping as DuckDB; use DuckDB |
| `DUCKDB_PROVEN_EMPTY` | DuckDB's proof copy eliminates all real join work; use DuckDB without SJs |
| `FORCE_OUTERYAN` | Changed candidate selected by the forced experiment mode |
| `FORCE_OUTERYAN_DIAGNOSTIC` | Complete candidate forced past grouping and cost selection for a targeted correctness run |
| `COST_OUTERYAN_BETTER` | Changed candidate passed the strict threshold and costs no more than DuckDB |
| `COST_OUTERYAN_WITHIN_LIMIT` | Changed candidate costs more than DuckDB but passed the strict threshold |
| `COST_OUTERYAN_STRETCH` | High-confidence candidate passed the relaxed `1.20` stretch threshold |
| `COST_OUTERYAN_LOW_SELECTIVITY` | Stats-backed unary selectivity at or below `0.35` admitted the candidate through the continuous low-selectivity tier |
| `COST_DUCKDB_BETTER` | Changed candidate exceeded the configured threshold |
| `COST_UNCERTAIN_FILTER_AMPLIFICATION` | Unknown-selectivity amplification guard rejected the candidate |
| `COST_UNAVAILABLE` | A finite comparison could not be produced |
| `OUTERYAN_FAILED` | OuterYan did not produce a complete candidate |

Supported root aggregate and DISTINCT queries enter the same candidate pipeline.
They use `candidate_total <= 1.20 * baseline_cost`, with neither
the stretch tier nor the low-selectivity relaxation. The gate deliberately does
not credit estimated aggregate-pushdown benefit. Aggregate pushdown runs only
after this gate selects the OuterYan candidate; a rejected candidate returns the
exact DuckDB baseline without an OuterYan-specific rewrite. Aggregation inside a
join skeleton remains `INAPPLICABLE`. The enabled decomposition paths cover the
grouped `MIN`, `MAX`, and `SUM` queries. Global `COUNT(*)` is decomposed into
partial counts below the joins and a root sum, with the root projection restoring
the original `BIGINT` type and empty-input value.

### Command-line options

```text
bash auto_test/experiment_onoff.sh [options]
  -b, --bin PATH      DuckDB CLI
  -n, --runs N        positive odd timed executions per configuration (default 5; median)
  -t, --timeout S     set both per-statement limits (default 600 each; 10 minutes)
      --duckdb-timeout S    independent DuckDB/OFF limit
      --outeryan-timeout S  independent OuterYan/ON limit
      --threads LIST  multi-thread counts (default "32"; also accepts 16,32)
      --query-type T  all|join|graph|aggregate (default all)
      --all           run each unique SQL once (default)
      --corpus-scope S  benchmark, job-regressions, or selectivity-stress
      --only FAMILY   select|agg|pred|graph|tpch|tpcds|job|bench|all
      --pattern GLOB  include matching labels
      --exclude GLOB  exclude matching labels; separate globs with |
      --limit N       global query cap; 0 means unlimited
      --query-list FILE  ordered corpus-relative SQL paths; requires --only all
      --capture-plans save OFF/ON EXPLAIN, trace, and detailed cost files
      --profile       enable phase and optimizer profiling (default)
      --no-profile    skip phase and optimizer profiling
      --check-correctness     compare all bare-query result multisets (default)
      --no-check-correctness  explicitly opt out of result comparison
  -o, --out FILE      exact text output path
```

The one-command build/data/experiment driver accepts the same built-in corpus
selection:

```bash
# Build release, prepare data, regenerate the unique corpus, and run all queries.
bash auto_test/run_all.sh

# Run only aggregate queries from the unique corpus.
bash auto_test/run_all.sh --query-type aggregate

# Explicit spelling of the default.
bash auto_test/run_all.sh --all
```

Unless `SKIP_BUILD=1` is set, every `run_all.sh` invocation compiles
`build/release/duckdb` before running the experiments. `--query-type` selects the
query type; generation always refreshes the complete unique corpus.

`select`, `agg`, and `pred` currently alias the graph family; they do not filter
the graph filenames further. `bench` expands to TPC-H, TPC-DS, and JOB. `--limit`
is global and follows that family order.

### Examples

```bash
# Four small graph queries, one 16-thread smoke run
GRAPH_DATASET=bitcoin OY_THREADS=16 \
bash auto_test/experiment_onoff.sh \
  --only graph --query-type graph --limit 4 --runs 1 --timeout 60

# Two three-relation aggregate queries from each benchmark family
TPCH_SF=1 TPCDS_SF=1 OY_THREADS=4 \
bash auto_test/experiment_onoff.sh \
  --only bench --query-type aggregate --limit 6 --runs 1

# Full TPC-H family
bash auto_test/experiment_onoff.sh --only tpch

# Force one valid OuterYan candidate for a bare-query correctness comparison
DUCKDB_OY_FORCE_CANDIDATE=1 \
bash auto_test/experiment_onoff.sh \
  --only tpcds --query-type join --limit 1 --check-correctness --capture-plans

# Skip JOB bushy-7 labels
bash auto_test/experiment_onoff.sh --only bench --exclude '*bushy7*'

# Small unique-corpus run using existing databases
SKIP_DATA=1 OY_THREAD_COUNTS="16 32" OY_RUNS=1 bash auto_test/run_all.sh \
  --only graph --limit 10 --capture-plans
```

The release build enables TPCH and TPCDS but does not build HTTPFS.
None of the four benchmark builders requires HTTPFS: network downloads use the
`curl` executable and JOB reads cached local Parquet. Build HTTPFS separately
only on hosts with compatible libcurl development headers.

The scale variables in the second example describe the prepared databases in
the report header; rebuild the databases first if they are not already SF1.

## Output

Without `--out`, one start timestamp identifies the run. For each requested
thread count `N` (only `32` by default), the result group is:

```text
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS_tN.txt
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS_tN.csv
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS_tN.plans/
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS_tN.profiles/
```

Each row records `experiment_group`, `corpus_revision`, `corpus_scope`,
`workload_category` and `query_class`. Query categories are `join`, `graph` and
`aggregate`; there are no per-version output files. Diagnostic scopes select
existing canonical query IDs.
`run_all.sh` includes the corpus label, for example
`experiment_onoff_benchmark_YYYYMMDD_HHMMSS_t16.csv` and
`experiment_onoff_benchmark_YYYYMMDD_HHMMSS_t32.csv`.

### Recover saved results after a statistics failure

Per-corpus TXT/CSV results are saved before combined statistics run. A Python
dependency failure during that final step does not require executing queries
again. The CSV analysis loader ignores an incomplete optional `pyarrow` package
that lacks `__version__`, with a warning; it changes no installed packages.
NumPy and pandas are still required for statistics and plots.

To reprocess all September 26 result logs, including v3 selectivity stress:

```bash
python3 auto_test/reprocess_experiment_logs.py \
  'auto_test/results/experiment_onoff_benchmark_20260926*_v[123]*.txt' \
  --output-dir auto_test/results/reprocessed_20260926
```

The separate output directory receives per-corpus CSVs, a combined CSV and
statistics directory for each run/thread setting, and `recovery_manifest.json`.
Original files are preserved. Matching sibling CSVs retain unrounded timings
and full optimizer phase maps; TXT fills missing rows. TXT-only recovery leaves
unlogged values unavailable. Historical `note=TIMEOUT` rows are labeled
`correct=TIMEOUT`; other errors and result mismatches retain their status.
Missing versions and incomplete query counts are reported, never filled with
fabricated results. Add `--csv-only` for standard-library-only recovery without
statistics dependencies.

With `--out path/name.txt`, a sweep writes `path/name_t16.txt` and
`path/name_t32.txt`, with matching CSV names. For a single configuration the
explicit output path is used unchanged. Each CSV contains one row per query
and records `aggregate_query`, `aggregate_pushdown_applied`, `timing_status`,
`timing_threads`, `tm_off`, `tm_on`, and `tm_speedup`. A `fallback-skip` row has
no fabricated runtime pair and records `tm_speedup=1.000` as a policy default. New outputs
contain no `t1_*` columns. Appended `profile_*` columns record status, actual
thread count, R1/R2/R3 operator work and counts, Other CPU work, wall latency,
total CPU work, phase shares, sample count, and the raw profile directory.
The `optimizer_*` columns record paired DuckDB/OuterYan total optimization time,
the measured workflow-phase sum, residual optimizer time, one-sample count, and
workflow-phase JSON maps. When profiling is disabled or skipped, these measurements
remain unavailable.
Each failed profiled query retains its post-warm-up OFF/ON JSON files, compact
decision trace, and CLI log. Successful intermediate profiles are deleted. Timed-out queries are not
retried, and no separate attempts CSV is produced.

Live stderr and the TXT report use one clearly separated block per query:

```text
====================================================================================================
[ 63/185] query=derived__example
  result: correct=TRUE timing=measured reorder=1 selected=OUTERYAN kernel=bitmap(b=3,h=0) threads=16 runtime_s=[DuckDB=12.000000000 OuterYan=6.000000000] speedup=2.000 optimization_s=[status=OK DuckDB=... OuterYan=...] measurement=[check=enabled protocol=warm-profile-then-timing-v1 samples=1 estimator=single_post_warmup warmups=2]
  context: family=tpch category=join nrel=5 pass=main note=OK ... breakdown_s=[status=OK CPU=... R1=... R2=... R3=... Other=...]
  decision: plan=[mode=GATED reason=COST_OUTERYAN_BETTER ... formula=...] optimizer_phases=[...] cost=[...] SJ=[...]
```

The record always uses four lines: query identity; result/runtime/optimization;
family and phase breakdown; and decision/formula details. Full workflow-phase
maps remain in CSV rather than making the live text block unreadable.
Applicable queries include the OuterYan and
DuckDB cost formula, gate comparison, and join/SJ weights on line 2. With plan
capture enabled, that line also lists the DuckDB-OFF and enabled EXPLAIN files,
full trace, and per-join/per-SJ cost records.

`pairs` counts planned semi-join applications in that round. `filters` counts
new filter constructions; a reused filter contributes another pair without
another filter. These are optimizer plan counts, not profile measurements.

Each query block includes:

| Field | Meaning |
|---|---|
| Line 1 | Query index and name |
| Line 2 | Correctness, reorder/selection, kernel, unprofiled runtime/speed-up, and optimizer totals |
| Line 3 | Family/category/path/pass, relation count, note, and phase breakdown |
| Line 4 | Decision mode, formula/cost operands, focused OuterYan pass timings, notices, and optional artifacts |

Each applicable, costed query includes raw cost components and an expanded
gate:

```text
gate formula: candidate_join + semijoin_ratio * semijoin_raw <= baseline_ratio * baseline
gate values:  <join> + <sj-ratio> * <raw-sj> <= <baseline-ratio> * <baseline>
gate result:  <candidate-total> <= <threshold> => PASS|FAIL -> <decision>
```

For same-grouping, inapplicable, unavailable, or forced-policy cases, the report
states that the numeric gate was skipped and prints the decision reason.

The CSV exports the same decision, cost, kernel, correctness, and timing
fields in machine-readable form, including the SQL-derived `relation_count`,
`default_filter_upper_bound_checked`, `default_filter_upper_bound_selected`,
`full_reduction_cardinality_lower_bound_applied`,
`uncertain_filter_amplification_guard`,
`stretch_cost_gate_eligible`, `stretch_cost_gate_selected`,
`unary_filter_selectivity`, `low_selectivity_cost_gate_eligible`,
`low_selectivity_cost_gate_selected`, `low_selectivity_cost_ratio_limit`,
`baseline_join_input_rows`, `candidate_join_input_rows`,
`candidate_to_baseline_join_input_ratio`,
`semijoin_retained_cardinality_ratio`,
`uncertain_filter_cardinality_amplification`, `round1_pairs`,
`round1_filters`, `round2_pairs`, and `round2_filters`.
`effective_pass` remains `main` for schema compatibility. The final text summary groups speed-ups separately by
`outer_reordered` and `outer_yan_selected`, and reports query, correct, and timed
counts for every relation depth present in the run.

### 统一实验结果入口

```bash
python3 auto_test/gen_experiment_result.py --date 20260926
```

该命令直接读取 `auto_test/results/experiment_onoff_*.csv`，一次性生成统计、
Matplotlib 图形和论文 LaTeX。默认输出位置根据输入实验日期决定，为
`auto_test/results/plots/20260926/`，与执行命令时的工作目录无关；只有需要覆盖
默认位置时才使用 `--output-dir DIR`。

`refresh_paper_results.py` 的论文更新也沿用此目录约定：默认放在
`auto_test/results/plots/YYYYMMDD/`；跨日期合并时使用最新参与实验的日期。
PDF、PNG、统计与 LaTeX 文件直接放在该目录下，不另建 `paper_refresh_*`
或 `figures/` 子目录。当前合并 20261008 与 20261010 的结果位于
`auto_test/results/plots/20261010/`。
论文更新同时输出 `execution_optimization_updates.tex`，包含最新 phase 汇总、
代表查询优化时间表及对应分析，可直接替换这两个 subsection；相同内容也写入
`paper_updates.tex`。优化时间采用两种配置的 `all_optimizers` 总时间，运行时间采用
预热后无 profiling 的实测中位数（当前为五次），不将 optimizer 专属 phase 之和替代总时间。

论文统计统一只使用双方完整实测且没有超时的 OuterYan-selected 配对。
20261011 固定协议：双方每条 statement（含五次计时中的每一次）各限时 **600 秒**，
不是五次合计 600 秒；默认仍为五次预热后无 profiling 计时，全部完成后取中位数。
使用 `--timeout 600` 可覆盖旧的 timeout 环境配置；不要额外设置其它单侧 CLI 限时。
**只要 DuckDB 或 OuterYan 任意一侧在任何阶段超时（含 correctness、warmup、kernel、
profile 或正式计时），整个 query 都不计入性能统计、有效 selected 数量或图中的数据点。**
不再用 600 秒或其它 timeout 上限替代实测时间。
`--duckdb-timeout-substitute` 已废弃，仅为兼容接受 `0`（默认）；`600` 会报错，
防止旧命令重新启用替代值。表、正文、整体图、phase 与优化时间样本使用同一超时排除规则。
原始 CSV 和部分完成的单侧计时不改；`timeout_queries.csv`、`timeout_summary.csv` 和
`reporting_excluded.csv` 保留诊断，`timeout_substitutions.csv` 为空（仅留列名兼容旧工具）。
已完成的亚秒级查询和实测减速案例保留，fallback/default 和精确的 $1\times$ 仍不计入论文性能集合。
所有新 SQL 在复测前均为 pending，不得沿用被替换查询的历史时间。

`--date` 也接受 `2026-09-26`。同一天存在多个线程数时，分别写入日期目录下的
`t16/`、`t32/` 等子目录，绝不合并线程配置。省略日期则按输入日期分别输出。
`--group-by run` 可将同一天的批次继续分开。显式传入 CSV 路径或 glob 也受支持。

同日同线程数组合按 SQL 身份跨旧版本去重，保留最新记录（包括失败），不按最快耗时挑选。
`(workload_category, family, query)` 相同的记录取最新批次，包括失败；旧批次只补
缺项。同批次 final CSV 优先于 attempts，per-version CSV 优先于 combined CSV。
不同版本的同名 query 是不同实例。每条结果的来源写入 `plot_selection.json`。

输出全部位于同一目录：

| 文件 | 内容 |
|---|---|
| `overview.pdf` | 总览、形状/关系数、runtime 与 phase 的多页图 |
| `speedup_all_queries.pdf/png` | 左图为全量实测 runtime 散点；右图只展示各 family 选中 OuterYan plan 的实测 speed-up；不显示顶部日期/版本标题 |
| `phase_breakdown_outeryan.pdf/png` | 代表查询的 R1/R2/R3/Other CPU 比例和无 profiling 的运行时间对照；仅有完整 profile 时生成 |
| `STATISTICS.md`, `statistics.json` | 有效实测统计、OuterYan-selected 性能综述、覆盖与排除原因、精确数值和输入哈希 |
| `benchmark_statistics.csv`, `phase_summary.csv`, `optimizer_*.csv` | 可进一步处理的速度、phase、optimizer 汇总 |
| `paper_statistics.tex` | 唯一的 LaTeX 输出，按 1–5 编号并用注释分隔线区分 benchmark 数量、性能分析、runtime 表、phase 表及优化开销表；重跑会清理旧版五个独立片段 |
| `paper_statistics.json` | 论文精确数值、各维度分组、代表 query 的 SQL/schema 来源、哈希及参与列清单 |
| `phase_queries.json`, `plot_selection.json` | phase 展示样本及所有输入记录的来源 |

`results/experiment_onoff_*.csv` 是原始逐 query 实验输入，需要保留。
日期输出目录内的 CSV 是统计汇总导出；JSON 保存精确统计、筛选/抽样记录、来源
与文件哈希，用于复核和复现。它们是可重新生成的辅助结果，不是绘图必须读取的
中间文件：脚本从原始 CSV 和 corpus manifest 重新计算，并在内存中绘图。

有效 query 必须正确、有完整有限正数 OFF/ON 实测时间，且 **至少一方达到 1 秒**。
双方都严格小于 1 秒的 pair、未执行 fallback、失败及超时均不计入有效总数。
Review 时可传 `--include-subsecond`，在图、统计、phase/optimizer 汇总和 LaTeX 中
统一保留双方都小于 1 秒的实测 pair；建议用 `--output-dir` 指定独立 review 目录。
该选项不纳入超时、错误或 fallback-skip，不按 speed-up 删点，也不修改原始 CSV。
未执行 fallback 原始 CSV 的 `1×` 占位不进入任何性能统计。原始 CSV 不修改；
JSON 的 `input_corpus` / `unique_queries` 保留过滤前输入数，`corpus` / `valid_queries`
记录有效实测数，覆盖记录保留每条排除原因。
论文性能综述和总体速度图只使用有效实测中 `selected_plan=OUTERYAN` 的 query；
runtime 表仍分别列出所有有效实测与 OuterYan-selected 两个子集，明确区分口径。
右图仅包含 `selected_plan=OUTERYAN` 且正确、实测时间完整的 query，speed-up
由 OFF/ON 时间重新计算；实测恰好为 `1×` 或慢于 DuckDB 的 OuterYan plan 仍保留。
右侧渐变箭头色块的实际上边缘与左图顶部对齐，绘图区底部及子图标题分别对齐；
箭身填满色条高度，不以文字或外侧留白作为对齐依据。说明文字放在箭头上方。
两图共享顶部的 benchmark 颜色图例。左图对角线下方用浅青蓝色标识 OuterYan 更快的区域。
右图背景采用柔和玫瑰粉 → 白色 → 青蓝色的双色渐变，白色对应 `1×`，并保留该位置的竖线。
右图上方的渐变箭头与背景共用同一颜色映射、横向范围和对数尺度，直接对应下方横坐标；
箭头指向更高加速比，上方两端标注 `OuterYan slower` / `OuterYan faster`，不重复显示刻度标签。
Geomean 对 query 等权，Total 为实测
`sum(OFF)/sum(ON)`，不伪造缺失 runtime 或 timeout 时长。

Phase 百分比按 operator CPU 秒加权，四部分之和对应 CPU time，不能解释为
wall-time 比例。Phase 图每个 family 默认取最多 15 条，由
`--phase-samples-per-benchmark N` 调整；优化表默认每个 family 最多 3 条，由
`--representatives-per-benchmark N` 调整。两种抽样都按 shape 和 OFF runtime
分位进行，不按 speed-up 挑选。全量统计不使用展示样本代替总体。

`--exclude-selectivity-stress` 同时从图、统计和
论文中排除 stress。生成这类不同口径时可指定另一个输出目录。
Optimization ratio 为各配置自己的 optimizer 时间 / 完整 unprofiled query runtime，
单位为百分比。

Attributes 按 SQL 中去重后的 `(表别名, 列名)` 计数，覆盖 SELECT、JOIN、WHERE、
GROUP BY、HAVING 和 ORDER BY。同一列重复出现只算一次，自连接的不同别名分别计数。
投影中的 `*`/`alias.*` 按实际数据库 schema 展开；`COUNT(*)` 本身不增加列。
脚本根据 canonical 路径或保留的原始类别和路径定位当前/历史 SQL，通过 DuckDB CLI
只读查询 `information_schema.columns`，不执行 benchmark SQL。数据库和 CLI 路径
沿用 `GRAPH_DB` / `TPCH_DB` / `TPCDS_DB` / `JOB_DB`、`DUCKDB_BIN` 的环境覆盖，
否则使用仓库根目录默认数据库和 release/debug CLI。缺少 SQL/schema 或遇到超出
当前单 SELECT join corpus 的语法时明确报错，不输出猜测值或 `--`；完整列清单与
来源哈希写入 `paper_statistics.json`。

论文可直接引用唯一的 `results/plots/YYYYMMDD/paper_statistics.tex`；编号和分隔线使用 LaTeX 注释，
便于在源文件内定位，不会额外显示在论文正文中。
例如：`\input{auto_test/results/plots/20260926/paper_statistics.tex}`。

实验 harness 自动使用同一文件的 `--statistics-only` 内部接口生成批次统计，
保留原本的批次 CSV 路径与输出协议。这条路径及日志恢复只需 NumPy/pandas，
不会导入 Matplotlib；完整绘图才需要 Matplotlib。pandas 的可选 pyarrow 兼容处理
也位于统一脚本中。旧 0916 结果是不同 corpus 的历史数据，不与 0926 混合。

## Optimizer trace

`DUCKDB_OYTRACE=/path/to/file` enables the file-based optimizer trace in release
and debug builds. It records the SQL, logical input, OT/OJT stages, semi-join
pairs, DuckDB baseline, cost comparison, final `[OY_DECISION]`, and selected plan.
Tracing adds planning and file-I/O overhead and should not wrap a timed execution.
The experiment harness avoids that by collecting its decision in a separate
traced `EXPLAIN` process.

`trace_outer_yan.sh` defaults to the debug CLI, but `-b` can select release:

```bash
# Trace a corpus file with release
bash auto_test/trace_outer_yan.sh \
  -b build/release/duckdb --db tpch_db \
  -f auto_test/outerjoin_benchmark/benchmark/tpch/derived__ojb_tpch_q03_order_revenue_ldmx.sql

# Trace inline SQL
bash auto_test/trace_outer_yan.sh \
  -b build/release/duckdb --db graph_db \
  -q "SELECT * FROM R1 LEFT JOIN R2 ON R1.dst=R2.src;"

# Trace the five historical R/S/T/K cases
bash auto_test/trace_outer_yan.sh -b build/release/duckdb --db graph_db fails
```

The graph builder creates R/S/T/K views, so no manual view setup is required.

## Order-aware semi-join reduction

After join reordering and re-simplification, the optimizer can shorten the
reduction schedule without changing the selected real-join tree. This is an
order-based rule, not a lower cost-gate threshold. Compare it within one binary:

```sql
SET disabled_optimizers TO '';
SET VARIABLE outer_yan_partial_reduction = false; -- reference schedule
-- Run the bare query.
SET VARIABLE outer_yan_partial_reduction = true;  -- default: guarded partial schedule
-- Run the same bare query again.
```

The reduction tree is rooted at a preserved endpoint of the first selected
join when possible. Preserved sides of the original simplified joins are never
reduced. Bottom-up reductions remain, except the first join may absorb its root
reducer when no top-down consumer depends on that root. Top-down reductions are
retained along the complete ancestor paths for inputs joined with a child first
or newly preserved by de-simplification. Other top-down reductions are omitted.
The selected expression must remain simple; unsupported predicates, unsafe
intermediate filters, and aggregate queries keep the reference schedule.
The partial schedule is adopted only when it has strictly fewer logical pairs.
Fewer pairs alone is not evidence of a runtime improvement.

Re-simplification checks the selected binary expression for NULL-padding safety
before restoring each original type. Semi-join filters are shared only within
one round: a top-down build must see any preceding top-down reductions, not a
cached bottom-up key set. Existing PK/FK pruning requires catalog-backed total
coverage (including non-null FK columns) and an unreduced, unfiltered build
input. A primary key alone does not imply that every probe has a match.

Cost-gate estimates still describe the reference reduction schedule. The
`executed_round1_pairs`, `executed_round2_pairs`, and corresponding `_filters`
fields describe the selected post-RBO plan separately. Keep the cost estimate
and executed count distinct when reviewing profiles. This optimization cannot
rescue a candidate already rejected by reference-schedule costing.

## Semi-join kernel controls

| Control | Current default | Effect |
|---|---:|---|
| `outer_yan_bitmap_max_bytes` | 32 GiB per filter | Bitmap budget; `0` forces hash |
| `outer_yan_hash_fn` | `duckdb` | Hash implementation; alternative is `murmur` |
| `outer_yan_stats_prefilter` | `false` | Use base min/max statistics to skip unsuitable bitmap attempts |
| `DUCKDB_SJ_KERNEL_TRACE` | unset | Emit finalized bitmap/hash kernel records |

Set session controls with DuckDB variables, for example:

```sql
SET VARIABLE outer_yan_bitmap_max_bytes = 0;
SET VARIABLE outer_yan_hash_fn = 'murmur';
SET VARIABLE outer_yan_stats_prefilter = true;
```

Kernel output uses `not-run`, `bitmap(b=N,h=0)`, `hash(b=0,h=N)`,
`mixed(b=N,h=M)`, or `none(b=0,h=0)`. Hash and mixed results also report
reason counts. Raising the bitmap budget can address `overflow` (and
`force_hash` after replanning), but not `ineligible` key types or composite
keys.

Disable the cohesive optimizer with:

```sql
SET disabled_optimizers TO 'outer_yan';
```

## One-command and manual workflows

```bash
# Build release and data, regenerate unique SQL, and compare Original/OuterYan.
bash auto_test/run_all.sh

# Run only one query type.
bash auto_test/run_all.sh --query-type join
bash auto_test/run_all.sh --query-type aggregate

# Reuse the existing binary, databases, and generated queries.
SKIP_BUILD=1 SKIP_DATA=1 SKIP_QUERY_GEN=1 bash auto_test/run_all.sh

# Run one custom corpus.
OY_CORPUS=/path/to/custom_corpus \
  SKIP_BUILD=1 SKIP_DATA=1 bash auto_test/run_all.sh --only bench
```

The comparison runs 720 unique candidates under `outerjoin_benchmark/benchmark`:
172 Graph, 176 TPC-H, 206 TPC-DS and 166 JOB. Fifteen TPC-DS three-tier extension
queries have SF50 measurements. Earlier exact measured speed-up <0.5
and TPC-DS timeout exclusions remain. The 20261008 frozen screen additionally
retires two Graph and nine JOB queries with observed speed-up <=0.7 in the
20261007_161108 full run. These are single-sample, unchecked performance results,
not correctness-verified evidence. Other families and timeout/fallback rows are
unchanged; normal regeneration does not restore the retired SQL.
The new TPC-DS run has completed: 47 of its 54 recovery candidates remain after
retiring seven measured regressions. Across the 194 previously tested TPC-DS definitions,
36 have complete measured pairs and 158 are fallback-skip; none timed out in
that run. Qualification is a separate measured filter; the active corpus is
performance-screened, not claimed to be exactly balanced or free of timeouts
in other families. Raw results and retired SQL remain available.
The harness checks one bare-query OFF/ON result pair for every query by default,
including fallbacks. After equivalence passes, it measures one post-warm-up
execution per side for performance-eligible queries. Explicitly unchecked rows
remain NOT-CHECKED and are never represented as verified-correct.
The default is 32 threads; `--threads "16 32"` produces separate result files.
The PostgreSQL replay workflow and its public wrappers have been removed.

Manual equivalent for the unified two-way benchmark stage:

```bash
BUILD_TPCH=1 BUILD_TPCDS=1 GEN=ninja make release
bash auto_test/build_db.sh all
python3 auto_test/gen_outerjoin_benchmark.py
OY_CORPUS=auto_test/outerjoin_benchmark/benchmark \
  bash auto_test/experiment_onoff.sh --only all
```

`run_all.sh` and `build_db.sh` reuse existing database files. Changing a TPC
scale selects a different scale-qualified default path, so the previous scale
can remain on disk. An explicit `TPCH_DB`/`TPCDS_DB` override must match the
requested scale; the filename is not a content check. Use a new path to retain
old data rather than `FORCE=1`, which rebuilds the chosen file.
