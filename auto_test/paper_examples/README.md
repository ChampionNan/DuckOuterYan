# 论文例子的单独测试

这个目录只保存手工指定的论文 SQL，不加入现有 benchmark corpus。
目前包含用户提供的 `customer LEFT JOIN (orders JOIN lineitem)` 例子；未指定论文名称或编号。

**较强收益的备选：** [超过 90 天的延期交付审计](tpch/orders_before_1997_receipts_over_90_days_late.sql)。
orders 使用 `o_orderdate < DATE '1997-01-01'`，lineitem 仅使用
`l_receiptdate > l_commitdate + INTERVAL '90 days'`，各一个比较条件。
当前 `0.20 / 1.20` 参数下正常通过 DP 和 gate；SF1、10 线程、独立 11 次为 **1.283×**，
追加 32 对交替计时为 **1.315×**，31 对 ON 更快，完整裸查询结果一致。
90 天是从 Q21 延期关系派生的业务阈值，并非标准 Q21 原文；这个业务范围比普通发货期间报表更窄。
普通截止点的初测高值没有稳定复现，详细对照和全部数据见 [PAPER_EXAMPLE.md](PAPER_EXAMPLE.md)。

在已有的真实 SF100 数据库上测试该版本（将 `--db` 替换为实际路径）：

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/orders_before_1997_receipts_over_90_days_late.sql \
  --db /path/to/tpch_sf100.duckdb \
  --threads 10 --runs 11 --timeout 600
```

使用当前 Release 构建；脚本不会生成数据，也不会通过 `--db` 自动改变 scale。
`--runs 11` 为每模式正式计时次数，`--timeout 600` 为每条语句的秒数上限。
正确性检查比较完整结果多重集，其 Python 内存需求随结果行数增长。
现有 SF100 统计外推仅验证计划选择，没有 SF100 性能实测结论。

**当前推荐，常见日期过滤且每表一个比较：** [已全部发货订单中、截止日前发货的明细](tpch/fulfilled_orders_shipped_before_april_1992.sql)。
使用 `o_orderstatus = 'F'` 和 `l_shipdate < DATE '1992-04-01'`，正常重排，参数保持 `0.20 / 1.20`。
SF1、10 线程、每模式 11 次为 **1.050×**，追加 32 对交替计时为 **1.097×**，31 对 ON 更快。

若允许一个 `BETWEEN` 日期范围谓词，[1994 年第一季度发货版本](tpch/fulfilled_orders_shipped_q1_1994.sql)
独立验证为 **1.145×**，交替复测为 **1.168×**，32 对中 30 对 ON 更快。
两个版本都完成裸查询完整结果校验和实际物理 grouping 验证；SQL、计数及所有样本见 [PAPER_EXAMPLE.md](PAPER_EXAMPLE.md)。
BETWEEN 在内部会拆为两个边界比较；严格要求单个比较时使用截止日版本。

**此前日期关系版本：** [截止日前下单、承诺日当天收货](tpch/orders_before_1997_received_on_commit_date.sql)。
使用 `o_orderdate < DATE '1997-01-01'` 和 `l_receiptdate = l_commitdate`，customer 不过滤，连接条件保持原样。
这是 Q3 截止日形式与 Q21 日期关系的业务变体：报告日期调整为 1997 年初，Q21 的 `>` 改为 `=`。
沿用当前 `0.20 / 1.20` 成本参数，正常采用 customer–orders 顺序；SF1、10 线程、每模式 11 次，
**27.757 → 19.228 ms（1.444×）**，完整结果 157,320 行，多重集一致。
语义、选择性和验证数据见 [PAPER_EXAMPLE.md](PAPER_EXAMPLE.md)。

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/orders_before_1997_received_on_commit_date.sql \
  --threads 10 --runs 11
```

若需追加一个不改变当前实际选择性的条件，可使用 [Q12 发货条件版本](tpch/orders_before_1997_on_commit_date_early_shipment.sql)，
增加 `l_shipdate < l_commitdate`。dbgen 的收货日期总晚于发货日期，因此在 `l_receiptdate = l_commitdate` 下，
新增条件不再过滤记录；SF1 前后均为 49,736 条 lineitem，完整查询结果也一致。
当前成本比和正常计划选择不变；新版本本次 11 次计时为 **28.762 → 18.463 ms（1.558×）**，
不能将跨轮计时差异归因于新增条件本身。详细证据见上述文档。

若将等号改成 [大于](tpch/orders_before_1997_received_after_commit_date.sql) 或
[小于](tpch/orders_before_1997_received_before_commit_date.sql)，并取消发货条件，仍正常选中目标 grouping，
但本次 SF1 未观察到稳定加速：每模式 11 次分别为 0.978× / 0.908×；
同连接三版本轮换、各 32 对交替计时分别为 0.972× / 0.932×（等号版 1.328×）。
实际 lineitem 保留比例从 0.83% 增至 63.21% / 35.96%，而成本比仍同为 1.159868。
完整对照、行数和原始样本见上述文档。

**两个 lineitem 条件的备选，原样使用标准谓词：** [已发货订单的延期折扣明细](tpch/fulfilled_orders_q6_discount_late_receipts.sql)。
orders 使用 Q21 的 `o_orderstatus = 'F'`；lineitem 使用 Q21 的 `l_receiptdate > l_commitdate`
和 Q6 的 `l_discount BETWEEN 0.05 AND 0.07`。客户不加过滤，连接条件不变，不使用 EXTRACT。
沿用当前 `0.20 / 1.20` 成本参数，DP 和 gate 正常选中 customer–orders；SF1、10 线程、每模式 11 次，
46.776 → 32.914 ms（1.421×），完整结果多重集一致。追加 32 对交替计时为 1.535×，32 对均加速。
它将此前的 orders 时间条件换回状态条件。语义、谓词来源和全部证据见 [PAPER_EXAMPLE.md](PAPER_EXAMPLE.md)。

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/fulfilled_orders_q6_discount_late_receipts.sql \
  --threads 10 --runs 11
```

以下保留先前候选和诊断结果。

**不引入额外数值阈值的版本：** [已完成订单中承诺日当天收货的明细](tpch/fulfilled_orders_received_on_commit_date.sql)。
使用 `o_orderstatus = 'F'` 和 `l_receiptdate = l_commitdate`，各表一个 unary predicate。
它借鉴 Q21 的日期比较业务，正常接受 customer–orders 顺序；SF1 追加 32 对交替计时加速 1.160×，
此前两轮独立验证为 1.199× / 1.025×。详细方法与全部结果见 [PAPER_EXAMPLE.md](PAPER_EXAMPLE.md)。

若 orders 也要时间条件，可用 [Q3 截止日版本](tpch/orders_before_cutoff_received_on_commit_date.sql)：
`o_orderdate < DATE '1995-03-15'` 配合 `l_receiptdate = l_commitdate`，正常重排，SF1 本次加速 1.140×。

[1997 截止日的跨年交付版本](tpch/orders_before_1997_cross_year_on_commit_date.sql) 是先前使用 EXTRACT 的探索记录，
SF1 独立验证为 1.537×，交替对照为 1.412×。对照显示较大收益主要来自截止日变化；
仅在原 1995 截止日追加谓词未显示明显增强，不能把收益归因于跨年谓词本身。

**各轮论文候选：** [有业务语义的 SQL、算法决策与 SF1 数据](PAPER_EXAMPLE.md)。
该实例只调整 unary predicates，由 DP 自然选择 customer–orders 先连接，默认 ON 实际采用该计划。
当前实验构建将 SJ 成本权重设为 0.20；下文先前的 SF1/SF100/门控诊断使用权重 1.0，属于历史对照。

**只调整 orders / lineitem 的性能正例：** [已完成订单的延期折扣明细](tpch/fulfilled_orders_late_discounted_lines.sql)。
customer 不加过滤，保持当前参数并正常通过 gate；SF1 两轮独立验证各 11 次，分别加速 1.221× / 1.250×。
完整 SQL、成本决策、复现命令和原始数据位置见 [PAPER_EXAMPLE.md](PAPER_EXAMPLE.md)。

更简单的 [单一 lineitem 谓词版本](tpch/fulfilled_orders_large_quantity_lines.sql) 保持订单状态条件，
仅使用 `l_quantity >= 50`；正常接受 customer–orders 顺序，SF1 两轮实测加速 1.210× / 1.137×。
它替换业务筛选条件，与前述三谓词查询不等价。

在仓库根目录运行：

```bash
python3 auto_test/paper_examples/run_example.py --threads 10 --runs 11
```

另外执行强制 OuterYan 候选诊断：

```bash
python3 auto_test/paper_examples/run_example.py --threads 10 --runs 11 --force-candidate
```

其他论文例子可通过 `--query path/to/example.sql --db path/to/database` 单独运行。
输入应是一个返回标量列的 SELECT。`--bin` 可指定其他 Release 可执行文件；脚本不负责编译或生成数据。
结果默认保存到 `auto_test/results/paper_<query>_<timestamp>/`。

测试步骤：

1. 保存 OFF/ON 的逻辑、物理计划及 OuterYan decision trace。
2. 执行原始 SELECT，比较完整 CSV 记录的多重集，保留重复行，不添加 CTAS、COPY、LIMIT 或 ORDER BY。
   同时检查裸查询与 EXPLAIN 的选择结果一致。
3. 仅对结果正确的模式计时。回退到 DuckDB 计划的 ON 也照常测量。
   每个模式分两个进程批次执行，第二批反转模式顺序；每批先预热两次，随后计时。
   关闭 tracing/profiling，用 CLI trash 模式消费结果；耗时包含优化和结果消费，不包含 CSV 格式化。
4. 单独采集 JSON profile，保存原始时间样本、汇总和错误信息。

`--force-candidate` 使用已有的 `DUCKDB_OY_FORCE_CANDIDATE=1` 诊断开关，绕过同 grouping 回退及 cost gate。
它不代表默认 ON 行为，也不保证产生不同 grouping。任何模式错误或结果不一致时，该模式不计时，报告保留错误，脚本返回 1。
正确性比较在 Python 内存中保存结果多重集，适合这种小规模单例实验；CSV 的 NULL 标记为 `__PAPER_SQL_NULL__`，输入字符串不应使用该保留值。

## 在现有 SF1 上强制先连接 customer–orders

在仓库根目录运行：

```bash
python3 auto_test/paper_examples/run_forced_order.py --threads 10 --runs 11
```

用 `--db /path/to/tpch_db` 指定现有数据库，`--build-dir /path/to/build/release` 指定包含头文件对应版本共享库的构建目录，
`--out /path/to/new-results` 指定新结果目录。脚本需要 C++17 编译器以及现有 `libduckdb.dylib` 或 `libduckdb.so`。
它只编译一个小型实验程序，不重新编译或修改 DuckDB 库，也不改写源数据库。

原始 SQL 保持不变。实验程序通过进程内的 optimizer callback 调用现有 OuterYan Pre/DP/Post：
先记录原查询的两轮 semi-join reduction，再把 Desimplify 后的 OT 固定为
`(customer LEFT reduced_orders) LEFT reduced_lineitem`，最后交给现有执行器执行。
这里“先连接 customer–orders”指两个真实 join 的先后；前置 semi-join 仍需按原有两轮顺序完成。
每次查询都验证最终 grouping，独立 profile 再验证执行中的物理 grouping。

为了固定顺序并绕过当前 SJ 列位置在列裁剪后失效的问题，两个强制模式均禁用
`outer_yan,join_order,unused_columns`，由 callback 显式执行 OuterYan。
这是一项诊断实验，不表示默认门控会选择这个计划，也不是对列映射缺陷的修复。
不要直接将原 SQL 改成两层 LEFT JOIN：没有前置 reduction 时，这通常不等价。

脚本包含五个模式，均使用同一个 Release 共享库、同一份原始 SF1 数据：

- `off`：标准 OuterYan OFF。
- `on`：标准 OuterYan ON。
- `controlled_off`：禁用同样的三个优化器，但没有 SJ reduction，作为诊断设置对照。
- `sj_original`：强制执行 OuterYan 的原 grouping，先 orders–lineitem。
- `sj_customer_first`：同一组 reducer 下，固定先 customer–orders。

两个 `sj_*` 模式唯一不同的人工干预是 OT grouping；后续 lowering 可随之改变 join kind、build/probe 方向等。
所有模式先比较裸查询完整多重集，全部一致后才计时。计时是 C++ `SendQuery`/`Fetch` 的完整 planning + execution + drain，
不包括逐行转成字符串；每模式分两批进程执行，每批预热两次，第二批反转模式顺序。profile 单独采集。

2026-09-29 本机结果（10 线程、各 11 次）：

| 模式 | 中位数 | 非根真实 join 输出 |
|---|---:|---:|
| OFF | 21.622 ms | 130,393 |
| ON | 22.163 ms | 130,393 |
| 相同禁用设置的 OFF | 22.519 ms | 130,393 |
| 强制 SJ，orders–lineitem 先连 | 45.200 ms | 130,393 |
| 强制 SJ，customer–orders 先连 | 49.554 ms | 188,108 |

五个模式的完整结果多重集均一致，都是 219,240 行。
customer–orders 先连比同设置下的 SJ 原顺序中位数慢约 9.6%，是标准 OFF 的约 2.29 倍耗时。
customer-first 的本次样本有三个较大值（72–109 ms），已原样保存，没有删除；以上使用全部 11 个样本的中位数。
这份 SF1 上没有观察到该重排的性能收益。

产物：[报告](../results/paper_forced_order_20260929_172109/summary.md)、
[汇总 CSV](../results/paper_forced_order_20260929_172109/summary.csv)、
[全部计时样本](../results/paper_forced_order_20260929_172109/timing_samples.csv)、
[目标物理计划](../results/paper_forced_order_20260929_172109/sj_customer_first.plan.txt)、
[目标查询完整结果](../results/paper_forced_order_20260929_172109/sj_customer_first.rows.tsv)。
结果 TSV 使用 SQL literal 表达 NULL/字符串/数值，适合检查和逐行比较，不是原表数据的导入格式。

## 只替换为 SF100 外推统计，观察计划选择

```bash
python3 auto_test/paper_examples/run_stats_whatif.py
```

脚本编译独立的统计注入程序，链接已有 Release 库，不修改优化器源码和数据库。
它对原始例子运行 EXPLAIN 和 DP 成本诊断，不执行大规模查询，也不报告 SF100 性能。
与强制顺序实验相同，可用 `--db`、`--build-dir`、`--out` 指定路径。

本地没有真实 SF100 统计快照，因此采用明确的外推假设：三张表行数、四个连接键的 NDV 和键最大值乘以 100，
日期、shipmode 等其他列统计保持不变。SF1 对照使用乘数 1。注入覆盖正常 DuckDB baseline 与 OuterYan candidate。
此处 lineitem 外推行数为 600,121,500；这不是声称真实 SF100 恰好有这些行。

2026-09-29 结果：

| 统计 | DP：orders–lineitem 先连 | DP：customer–orders 先连 | 最终选择 |
|---|---:|---:|---|
| SF1 | 389,424.320 | 396,216.006 | DuckDB 原 grouping |
| SF100 外推 | 38,942,907.587 | 39,621,755.646 | DuckDB 原 grouping |

这些是正常过滤估计下、同一组 reducer 的真实 join 成本，未加固定 SJ 工作量。
customer–orders 先连的估计成本仍高约 1.74%。放大规模基本不改变选择率和成本比值，只有整数取整的小偏差。
完整选择仍为 `outer_reordered=0 reason=DUCKDB_PLAN cost_gate_applied=0`；没有因为规模放大而自动选择目标顺序。
trace 中保守过滤场景的候选总成本/基线成本仍约为 6.249，超过 1.20 上限；但实际先由同 grouping 规则回退。
真实 SF100 重新采集的近似 NDV 可能不同，需要该快照才能判断真实统计下的结果。

产物：[报告](../results/paper_stats_whatif_20260929_173354/summary.md)、
[SF100 外推计划](../results/paper_stats_whatif_20260929_173354/sf100.plan.txt)、
[SF100 decision trace](../results/paper_stats_whatif_20260929_173354/sf100.trace.txt)、
[统计和 DP 成本明细](../results/paper_stats_whatif_20260929_173354/sf100.details.txt)。

## 只改 unary predicate，保留原始 join condition

以下记录的是 SJ 权重调整前（1.0）的结果。
[customer_orders_lineitem_dp_customer_first.sql](tpch/customer_orders_lineitem_dp_customer_first.sql)
只去掉原查询的 `l_shipmode = 'AIR'`。日期范围、两条 join condition 和 SELECT 列均不变。
现有 DP 自然选中 customer–orders 先连接，但最终门控仍拒绝：
`outer_reordered=1 selected_plan=DUCKDB reason=COST_DUCKDB_BETTER`。
不要将该文件当作默认 ON 已采用 OuterYan 的例子。

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/customer_orders_lineitem_dp_customer_first.sql \
  --threads 10 --runs 5
```

180 组仅改普通一元谓词的搜索中，66 组产生新 grouping，全部被 gate 拒绝。
当前固定 SJ 工作计费与 1.20 门槛的下界推导说明：在该三表原始连接键和当前统计下，
普通一元过滤无法让这个候选通过门控。代码和参数没有修改。
裸查询 ON/OFF 结果均为 977,354 行，多重集一致；实际执行仍是 DuckDB grouping。

[完整报告、成本下界与实验数据](../results/paper_predicate_search_20260929/unary_only_report.md)。

## 本次结果：2026-09-29

使用本地现有 `build/release/duckdb`，CMake 配置为 Release，未重新编译。
可执行文件 SHA-256 保存在结果 JSON 中。
数据库为本地 `tpch_db`，表规模对应 SF1：customer 150,000、orders 1,500,000、lineitem 6,001,215。
注意 `configs.sh` 的默认 SF 参数不能代表已有数据库的实际大小。

10 线程，每模式 11 次计时，结果如下：

| 模式 | 最终选择 | grouping 改变 | 正确性 | 中位数 |
|---|---|---|---|---:|
| OFF | DuckDB | 不适用 | 219,240 行 | 22.541 ms |
| 默认 ON | DuckDB | 否 | 与 OFF 完全一致 | 22.898 ms |
| 强制候选诊断 | OuterYan | 否 | 执行错误，未计时 | — |

默认 ON 的决策为：

```text
selected_plan=DUCKDB
outer_reordered=0
outer_yan_selected=0
cost_gate_applied=0
reason=DUCKDB_PLAN
```

两者实际都先对 orders 做日期过滤、对 lineitem 做 AIR 过滤，完成 orders/lineitem 的 INNER HASH JOIN，
再与 customer 做 LEFT HASH JOIN。没有应用新的 join grouping，也没有执行 OuterYan 的 SJ 算子。
profile 中 orders 过滤后为 228,637 行，内连接输出为 130,393 行，最终输出为 219,240 行。
默认 ON 的中位数约高 1.6%，单次样本存在波动；本次没有观察到性能收益，不能用它证明新重排计划有效。

回退的直接原因是 grouping 相同，而不是 cost gate 拒绝。
trace 同时记录候选估计总成本 11,172,371.14、DuckDB 基线 1,787,793.89（约 6.25 倍），
其中候选两轮 semi-join 的估计工作量为 9,388,522。这些是模型估计值，不是执行耗时。

强制诊断生成了两轮 SJ，但执行报错：

```text
INTERNAL Error: Attempted to access index 2 within vector of size 2
KeyBitmap::ProbeBatch -> PhysicalSJProbe::ExecuteInternal
```

强制计划中 orders 分支的 `filter#1: probe #2` 与仅含两列的输入不一致，提示 probe 列位置映射问题。
这里只保留复现证据，未修改优化器或执行器；默认 ON 没有进入这条失败路径。

完整结果：

- [汇总](../results/paper_customer_orders_lineitem_20260929_164641/summary.md)
- [原始时间样本和决策](../results/paper_customer_orders_lineitem_20260929_164641/result.json)
- [默认 ON 计划](../results/paper_customer_orders_lineitem_20260929_164641/on.plan.txt)
- [默认 ON trace](../results/paper_customer_orders_lineitem_20260929_164641/on.explain.trace.txt)
- [强制候选错误栈](../results/paper_customer_orders_lineitem_20260929_164641/forced.correctness.stderr.txt)
- [DP 两种顺序的成本及选择率分析](../results/paper_customer_orders_lineitem_20260929_164641/cost_analysis.md)
