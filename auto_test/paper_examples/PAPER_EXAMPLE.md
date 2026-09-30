# 有业务语义、由 DP 自然选中的三表重排例子

## 更强收益的备选：单一严重延期条件（2026-09-30）

在每个过滤表仅一个比较条件、保持普通业务语义和当前参数的约束下，
进一步验证了 [超过 90 天的延期交付审计](tpch/orders_before_1997_receipts_over_90_days_late.sql)：

```sql
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate > l_commitdate + INTERVAL '90 days'
) ON c_custkey = o_custkey;
```

业务含义：审查 1997 年前下单、实际收货晚于承诺日超过 90 天的明细，保留没有此类明细的客户。
orders 从 F 状态改为下单截止日；lineitem 是一个带常量日期偏移的比较，没有额外的 AND 条件。
它由 Q21 的延期日期比较派生，**90 天是显式的严重延期报告参数，不是 Q21 原样谓词**，
也不是用户已有 SLA 的假定。该业务范围比普通发货期间报表更窄。

没有修改源码、成本权重、统计或 join condition；SJ 权重仍为 `0.20`，gate 上限仍为 `1.20`。
DP 自然选择 customer–orders，裸 SELECT 和 EXPLAIN 都正常通过门控，成本比 **1.159868**，
原因为 `COST_OUTERYAN_WITHIN_LIMIT`，无 force。物理 profile 验证目标 grouping 和三个 SJ probes。
SF1、10 线程，完整裸 SELECT 的 OFF/ON 多重集一致，共 **198,490 行**，
其中匹配明细 111,769 行、无匹配客户 86,721 行。

| 验证方式 | OFF 中位数 | ON 中位数 | OFF / ON |
|---|---:|---:|---:|
| 每模式 11 次独立验证 | 38.820 ms | 30.267 ms | 1.283× |
| 追加 32 对交替计时 | 39.639 ms | 30.136 ms | 1.315× |

追加实验在同一预热连接中轮换五个固定查询，各 32 对相邻 OFF/ON、交替模式顺序；
每个查询/模式预热三次，SET 不计时，裸 SELECT 完整消费，trace/profile 关闭，保留所有样本。
严重延期版 31 / 32 对 ON 更快。同轮旧截止日与季度版本分别为 **1.150× / 1.139×**，
因此本次更强收益有同时段的旧查询对照；不把单次探索计时的较高比值当作结论。

延期条件保留 **147,947 / 6,001,215（2.47%）** 的 lineitem，SJ 将 orders 从
**1,138,594** 行约简到 **106,415** 行，两个真实 join 的输入合计从 **1,547,524** 降至 **561,320** 行。
这些数据说明该条件有足够过滤能力，性能结论限于当前 SF1 实例。

本轮探索 34 个组合，其中 22 个正常重排。两个普通截止日的初测分别出现 1.28× / 1.38×，
但独立复测只有 **1.020× / 0.969×**；追加交替对照为 **1.132× / 1.105×**，没有稳定超过旧日期版本。
仅调整普通截止点，当前尚未验证出明显更强的收益。若不接受严重延期这一业务范围，应保留下面的普通日期版本，
而不能宣称已找到同样普通日期语义的稳定 1.3× 候选。

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/orders_before_1997_receipts_over_90_days_late.sql \
  --threads 10 --runs 11
```

本机产物（不随仓库提交）：[完整筛选及验证汇总](../results/paper_stronger_common_predicates_20260930/validation_summary.json)、
[独立验证与原始样本](../results/paper_orders_before_1997_receipts_over_90_days_late_20260930_143345/result.json)、
[物理 grouping](../results/paper_orders_before_1997_receipts_over_90_days_late_20260930_143345/verified_physical_groupings.json)、
[五版本交替计时全部样本](../results/paper_stronger_common_predicates_20260930/paired_comparison.json)。

### 该严重延期版本的 SF100 统计外推检查

工作区只有 SF1 的 `tpch_db`，尚无该查询的真实 SF100 性能结果。
对当前 SQL 使用现有 planning-only 工具，将表行数、四个连接键的 NDV 和键最大值放大 100 倍，
其他统计保持 SF1 值；只读原库，不执行 SF100 查询。这不是真实 SF100 采集统计。
SF1 对照的成本和决策与此前裸查询一致，放大行数及 NDV 已校验。

| 统计场景 | DP grouping | 最终选择 | 候选 / baseline 成本 |
|---|---|---|---:|
| SF1 | customer–orders 先连 | OUTERYAN | 1.159867522 |
| SF100 外推 | customer–orders 先连 | OUTERYAN | 1.159870247 |

参数仍为 `0.20 / 1.20`，两个场景都正常通过 gate，未强制候选。
结论仅支持等比例统计变化下的计划选择稳定；不能由此宣称 SF100 加速超过 SF1 的 1.28–1.32×。
扫描和 SJ 工作量也会增长，真实执行时内存、缓存和磁盘溢写会影响结果，论文中的 SF100 性能必须另行实测。

本机产物（不随仓库提交）：[报告](../results/paper_late90_sf100_planning_20260930/summary.md)、
[统计与决策](../results/paper_late90_sf100_planning_20260930/result.json)、
[SF100 外推计划](../results/paper_late90_sf100_planning_20260930/sf100.plan.txt)。

## 当前推荐：普通发货截止日或季度报表条件（2026-09-30）

如果希望 orders / lineitem 各一个条件，且不用罕见日期相等关系或额外数量/折扣阈值，
可使用 **已全部发货的订单中，指定报告截止日前发货的明细**：

```sql
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_shipdate < DATE '1992-04-01'
) ON c_custkey = o_custkey;
```

[截止日 SQL](tpch/fulfilled_orders_shipped_before_april_1992.sql) 严格只有一个 orders 比较和一个 lineitem 比较。
customer 不过滤，两个连接条件不变。F 表示所有订单明细已发货，来自 Q21；
发货截止日是 Q1/Q6 等查询使用的普通日期筛选形式，本例将报告截止日设为 1992-04-01。
它与此前“orders 下单截止日 + lineitem 日期相等”的查询含义不同。

如果接受一个 SQL `BETWEEN` 范围谓词，[1994 年第一季度发货版本](tpch/fulfilled_orders_shipped_q1_1994.sql) 更像常见季度报表：

```sql
AND o_orderstatus = 'F'
AND l_shipdate BETWEEN DATE '1994-01-01' AND DATE '1994-03-31'
```

lineitem 只有一个 `BETWEEN` 范围谓词，但优化器内部会将其拆为两个边界比较；
如果“一个 predicate”的定义要求拆解后也只有一个比较，应使用前面的截止日版本。
`l_shipdate` 为 DATE，所以包含 3 月 31 日整天。季度范围借用 Q6/Q14 的发货报告期间形式，
日期参数经过调整，不能称为完整或原样的标准 benchmark 查询。

两个候选均保持 SJ 权重 `0.20`、gate 上限 `1.20`，无 force、统计注入或源码参数修改。
DP 自然选择 customer–orders，实际 profile 确认该 grouping 和三个 SJ probes；
成本比均为 **1.122817**，正常接受原因 `COST_OUTERYAN_WITHIN_LIMIT`。
候选估计成本高于 baseline 约 12.28%，处于当前 20% 的容忍范围内。

SF1、10 线程，每模式 11 次独立验证，完整裸 SELECT 多重集均一致：

| 版本 | 结果行数 | OFF 中位数 | ON 中位数 | OFF / ON |
|---|---:|---:|---:|---:|
| 发货日期早于 1992-04-01 | 203,320 | 21.198 ms | 20.181 ms | 1.050× |
| 1994 年第一季度发货 | 315,171 | 23.128 ms | 20.193 ms | 1.145× |

由于收益幅度较小，追加同一预热连接中轮换这两个固定查询，各 32 对相邻 OFF/ON，
交替模式顺序、每模式/查询预热三次，SET 不计时，裸 SELECT 完整消费，trace/profile 关闭，保留所有样本：

| 版本 | OFF 中位数 | ON 中位数 | OFF / ON | ON 更快的对数 |
|---|---:|---:|---:|---:|
| 发货日期早于 1992-04-01 | 20.591 ms | 18.771 ms | 1.097× | 31 / 32 |
| 1994 年第一季度发货 | 23.796 ms | 20.367 ms | 1.168× | 30 / 32 |

两种计时安排分别报告，不只引用较好一轮。普通日期过滤可以满足“正常重排且实测加速”，
但这些实例收益约 5%–17%，没有重现此前日期相等实例的 1.4–1.5×。
截止日版本选中 **84,502（1.41%）** 条 lineitem，将 orders 从 **729,413** 行约简到 **38,276** 行；
季度版本选中 **224,122（3.73%）** 条 lineitem，将 orders 约简到 **94,296** 行。
收益仍依赖这个报告期间在 SF1 上的选择性，不意味着任意截止日或季度都加速。

本轮仅探索同一三表例子的 32 个常见 unary-predicate 组合，26 个通过正常门控并重排。
运输方式过滤被 gate 拒绝；退货标记和 open 状态配合延期收货的探索计时没有收益。
所有筛选结果保留；正式候选另做了完整结果、计划和交替计时验证。

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/fulfilled_orders_shipped_before_april_1992.sql \
  --threads 10 --runs 11
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/fulfilled_orders_shipped_q1_1994.sql \
  --threads 10 --runs 11
```

本机产物（不随仓库提交）：[筛选及验证汇总](../results/paper_common_single_predicates_20260930/validation_summary.json)、
[32 对交替计时全部样本](../results/paper_common_single_predicates_20260930/paired_comparison.json)、
[截止日版本独立验证](../results/paper_fulfilled_orders_shipped_before_april_1992_20260930_141718/result.json)、
[季度版本独立验证](../results/paper_fulfilled_orders_shipped_q1_1994_20260930_141739/result.json)。

## 日期相等版本：orders 与 lineitem 各一个比较谓词（2026-09-30）

[完整 SQL](tpch/orders_before_1997_received_on_commit_date.sql)：

```sql
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate = l_commitdate
) ON c_custkey = o_custkey;
```

业务含义：查看 **1997 年前下单、恰好在承诺日当天收货的明细**，并保留没有匹配明细的客户。
customer 继续不加过滤；orders 和 lineitem 各一个比较谓词，连接条件保持原样。
这里的“当天”是日期相等，不能描述成包含提前收货的“按时或提前”。
该版本取消了折扣区间，orders 从 F 状态条件换成报告截止日条件。

来源需准确标注：orders 借用 [Q3](../../extension/tpch/dbgen/queries/q03.sql) 的截止日形式，
报告日期从标准查询的 1995-03-15 调整为 1997-01-01；lineitem 借用
[Q21](../../extension/tpch/dbgen/queries/q21.sql) 的交付日期关系，将延期的 `>` 改成当天收货的 `=`。
因此这是 **TPC-H 业务谓词的派生实例**，不能称为逐字采用标准 Q21 谓词。

保持当前 SJ 权重 `0.20`、gate 上限 `1.20`，没有 force、统计注入或源码参数修改。
裸查询与 EXPLAIN 均为 `outer_reordered=1 selected_plan=OUTERYAN`，
成本比 **1.159868**，接受原因 `COST_OUTERYAN_WITHIN_LIMIT`。
物理 profile 确认 OFF 先连接 orders–lineitem，ON 在两轮 SJ 后先连接 customer–orders，共三个 SJ probes。

SF1、10 线程、每模式 11 次，OFF / ON 中位数为 **27.757 / 19.228 ms（1.444×）**。
完整裸 SELECT 多重集一致，共 **157,320 行**：37,842 条匹配明细、119,478 条无匹配客户记录。
SJ 将 orders 从 **1,138,594** 行减至 **37,181** 行，两个真实 join 的输入合计从
**1,375,927** 行降为 **381,682** 行。
在本 SF1 数据中，日期相等条件选中 **49,736 / 6,001,215（约 0.83%）** 的 lineitem，
所以本例仍依赖较强的实际过滤选择性，不能推广成任意单谓词均可加速。

本轮另检查了七个原样来自 Q1/Q3/Q6/Q12 的单一 lineitem 谓词，配合 Q21 的 F 状态；
它们虽正常采用目标顺序，探索计时未显示收益。先前仅保留 Q21 延期条件的版本同样较慢。
这些是已检查实例的结果，不是所有标准谓词组合都不可能加速的证明。

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/orders_before_1997_received_on_commit_date.sql \
  --threads 10 --runs 11
```

本机产物（不随仓库提交）：[完整验证及全部计时样本](../results/paper_orders_before_1997_received_on_commit_date_20260930_135143/result.json)、
[物理 grouping](../results/paper_orders_before_1997_received_on_commit_date_20260930_135143/verified_physical_groupings.json)、
[单谓词筛选](../results/paper_one_predicate_each_20260930/screening.json)、
[验证汇总](../results/paper_one_predicate_each_20260930/validation_summary.json)。

### 可选追加：不改变当前实际选择性的 Q12 发货条件

在上述单谓词版本中追加：

```sql
AND l_shipdate < l_commitdate
```

该条件原样来自 [TPC-H Q12](../../extension/tpch/dbgen/queries/q12.sql#L24)，
含义是“承诺日前发货”；配合 `l_receiptdate = l_commitdate`，表示“承诺日前发货、承诺日当天收货”。
[完整 SQL](tpch/orders_before_1997_on_commit_date_early_shipment.sql) 保持 orders 一个条件、lineitem 两个条件。

本仓库 [dbgen](../../extension/tpch/dbgen/build.cpp#L186) 将收货日期设为发货日期加上
[1–30 天](../../extension/tpch/dbgen/include/dbgen/dss.h#L323)。因此在 dbgen 数据上：
`receipt = commit` 加上 `receipt > ship`，可推出 `ship < commit`。
新增谓词相对于原条件是冗余的，有业务含义，但在当前生成数据中不再筛掉记录；这是数据生成规则的蕴含，
不是对任意 SQL 数据都成立的等价变换。

SF1 实际计数：原条件选中 **49,736** 条 lineitem，追加后仍为 **49,736** 条，
条件保留率 **100%**，联合选择性仍约 **0.83%**。
另执行修改前后两个裸 SELECT，完整结果多重集一致，均为 **157,320 行**；
新增版本的 OFF/ON 完整多重集也一致。

当前成本模型的 baseline、candidate 总成本和成本比均未改变：仍为 **1.159868**，
沿用 `0.20 / 1.20` 参数正常通过 gate，DP 和物理 profile 仍为 customer–orders 先连接、三个 SJ probes。
本次 SF1、10 线程、每模式 11 次，OFF / ON 中位数 **28.762 / 18.463 ms（1.558×）**。
与此前单谓词版本的计时差异不能证明追加谓词本身带来额外加速；本次结论是结果、实际选择性和成本选择保持一致，
且新增版本的 ON 仍有实测收益。

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/orders_before_1997_on_commit_date_early_shipment.sql \
  --threads 10 --runs 11
```

本机产物（不随仓库提交）：[计数、修改前后结果及成本验证汇总](../results/paper_orders_before_1997_on_commit_date_early_shipment_20260930_135715/predicate_validation_summary.json)、
[完整 OFF/ON 验证与计时样本](../results/paper_orders_before_1997_on_commit_date_early_shipment_20260930_135715/result.json)、
[物理 grouping](../results/paper_orders_before_1997_on_commit_date_early_shipment_20260930_135715/verified_physical_groupings.json)。

### 将收货日期等号改成大于或小于，并取消发货条件

保持 `o_orderdate < DATE '1997-01-01'`、customer 不过滤、原始连接条件和所有参数不变，
lineitem 仅使用以下一个比较条件，均不带 `l_shipdate < l_commitdate`：

- [延期收货版本](tpch/orders_before_1997_received_after_commit_date.sql)：`l_receiptdate > l_commitdate`，原样来自 Q21。
- [提前收货版本](tpch/orders_before_1997_received_before_commit_date.sql)：`l_receiptdate < l_commitdate`，为相反方向的业务变体。

两者都由 DP 自然选择 customer–orders，正常通过 gate，物理 profile 确认两个 grouping 和三个 SJ probes。
两个查询分别执行裸 SELECT 的 OFF/ON 完整多重集比较，均一致；延期版 **2,928,361 行**，提前版 **1,690,184 行**。
不同比较符改变了业务查询结果，不要求三个版本彼此等价。

SF1、10 线程，每模式 11 次独立验证：

| lineitem 条件 | OFF 中位数 | ON 中位数 | OFF / ON |
|---|---:|---:|---:|
| `receiptdate > commitdate` | 47.801 ms | 48.894 ms | 0.978× |
| `receiptdate < commitdate` | 39.876 ms | 43.909 ms | 0.908× |

由于大于版本差异较小，又在同一预热连接中轮换 `=` / `>` / `<` 三种查询，
各执行 32 对相邻 OFF/ON，交替模式顺序；每种查询/模式预热三次，SET 不计时，
裸 SELECT 完整消费，trace/profile 关闭，全部样本保留。结果如下：

| lineitem 条件 | 全表过滤后行数及占比 | OFF 中位数 | ON 中位数 | OFF / ON | ON 更快的对数 |
|---|---:|---:|---:|---:|---:|
| `=` | 49,736（0.83%） | 28.503 ms | 21.466 ms | 1.328× | 31 / 32 |
| `>` | 3,793,296（63.21%） | 51.257 ms | 52.708 ms | 0.972× | 11 / 32 |
| `<` | 2,158,183（35.96%） | 44.556 ms | 47.799 ms | 0.932× | 8 / 32 |

结论：`>` 和 `<` 均能选到目标计划，但本次没有观察到稳定加速。
成本 trace 对这三种查询给出了相同的 baseline **7,027,350.201**、candidate **8,150,795.265**、
比值 **1.159868**，均在当前 `1.20` 门槛内，SJ 权重仍为 `0.20`。
当前估计没有区分这些列间日期关系的实际选择性差异。

实际 SJ 行数解释了收益变化：过滤后的 orders 起点均为 **1,138,594** 行，
等号版约简到 **37,181** 行；大于版仍有 **1,044,009** 行，小于版仍有 **861,857** 行。
相应地，第一轮 SJ 处理的 lineitem 从约 5 万条增长为约 379 万 / 216 万条。
不等号版本的约简较弱、SJ 处理量大，实测未能抵消新增 SJ 开销。
这里不能将“成本门控接受”当作“预测成本更低”或“实际必然加速”。

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/orders_before_1997_received_after_commit_date.sql \
  --threads 10 --runs 11
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/orders_before_1997_received_before_commit_date.sql \
  --threads 10 --runs 11
```

本机产物（不随仓库提交）：[三版本验证汇总](../results/paper_receipt_comparison_20260930/validation_summary.json)、
[全部交替计时样本](../results/paper_receipt_comparison_20260930/paired_comparison.json)、
[可回放 SQL](../results/paper_receipt_comparison_20260930/paired_comparison.sql)、
[大于版本独立验证](../results/paper_orders_before_1997_received_after_commit_date_20260930_140226/result.json)、
[小于版本独立验证](../results/paper_orders_before_1997_received_before_commit_date_20260930_140313/result.json)。

## 两个 lineitem 谓词的备选：直接采用 Q21 与 Q6（2026-09-30）

[完整 SQL](tpch/fulfilled_orders_q6_discount_late_receipts.sql)：

```sql
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_receiptdate > l_commitdate
       AND l_discount BETWEEN 0.05 AND 0.07
) ON c_custkey = o_custkey;
```

业务含义：查看所有明细均已发货的订单中，**享受 5%–7% 折扣但延期收货的明细**，
同时保留没有此类明细的客户。`l_extendedprice` 仍为折扣前行金额。
orders 只保留一个条件，lineitem 使用两个条件；customer 不过滤，两条 join condition 保持原样。
本版本将此前的 orders 时间条件换回订单状态条件，查询结果相应变化。

- `o_orderstatus = 'F'`、`l_receiptdate > l_commitdate`：直接来自仓库内的 [TPC-H Q21](../../extension/tpch/dbgen/queries/q21.sql)。
- `l_discount BETWEEN 0.05 AND 0.07`：直接来自 [TPC-H Q6](../../extension/tpch/dbgen/queries/q06.sql)，包括上下界常数。

这是由标准 TPC-H 谓词构成的三表外连接实例，不是完整的 Q6 或 Q21。
不需要 EXTRACT、hash、日期提取函数或额外数量阈值。此前 EXTRACT 版本仅保留为探索记录。

### 正常算法选择与实际执行

沿用当前 Release 构建的 SJ 成本权重 `0.20` 和 gate 上限 `1.20`，本次没有修改成本模型、
DP、统计信息或运行时，也没有使用 force。EXPLAIN 与裸 SELECT 的 trace 决策一致：

```text
selection_mode=GATED
outer_reordered=1
selected_plan=OUTERYAN
cost_gate_applied=1
reason=COST_OUTERYAN_WITHIN_LIMIT
raw_cost_ratio=1.1228165302651749
```

候选估计总成本为 **2,776,560.151**，baseline 为 **2,472,852.934**。
候选估计成本高约 12.28%，处于当前 20% 的容忍范围内，因此通过门控。
物理 profile 确认 OFF 先连接 orders–lineitem；ON 在两轮 SJ reduction 后先连接 customer–orders，
共三个 SJ probes。RIGHT JOIN 的显示来自物理子节点方向，grouping 确实改变。

### SF1 验证与收益

现有 `tpch_db`，10 线程；裸 SELECT 完整结果多重集一致，共 **553,900 行**，
其中 **498,989** 行为匹配明细，**54,911** 行为没有匹配明细的客户。

| 验证方式 | OFF 中位数 | ON 中位数 | OFF / ON |
|---|---:|---:|---:|
| 独立验证，每模式 11 次 | 46.776 ms | 32.914 ms | 1.421× |
| 追加 32 对交替计时 | 48.405 ms | 31.540 ms | 1.535× |

第一项使用单例 runner 的两个独立进程批次，各批预热两次，第二批反转模式顺序。
第二项与“仅有 Q21 延期条件”的控制查询在同一预热连接中轮换，各执行 32 对相邻 OFF/ON，
反转先后顺序；每种查询/模式预热三次，SET 不计时。两项都关闭 trace/profile，完整消费裸 SELECT，
包含优化耗时，保留所有正式样本，计时安排不同，分别报告。
新组合的 32 对中 ON 均更快；控制查询为 **38.291 / 45.768 ms（0.837×）**，只有 1 对 ON 更快。
这说明在本机 SF1 上，加入 Q6 折扣区间后，该业务变体确实获得收益；不推广为完整 Q6/Q21 或其他 scale 的结论。

实际 SJ 将 orders 从 **729,413** 行减至 **359,550** 行，lineitem 从 **1,034,861** 行减至 **498,989** 行。
两个真实 join 的输入行数合计从 **2,413,263** 降至 **1,423,000**。
这只是实际数据流的说明，总耗时还包含 SJ 构建、探测和物化成本。

本轮探索了 45 个普通 TPC-H 谓词组合，20 个正常采用新 grouping；先筛选，再对保留候选独立验证。
完整筛选结果保留，不应将其中五次样本的探索计时当作论文正式结果。

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/fulfilled_orders_q6_discount_late_receipts.sql \
  --threads 10 --runs 11
```

本机原始产物（不随仓库提交）：[独立验证与全部样本](../results/paper_fulfilled_orders_q6_discount_late_receipts_20260930_134423/result.json)、
[物理 grouping](../results/paper_fulfilled_orders_q6_discount_late_receipts_20260930_134423/verified_physical_groupings.json)、
[32 对交替对照](../results/paper_official_predicates_20260930/paired_comparison.json)、
[交替计时 SQL](../results/paper_official_predicates_20260930/paired_comparison.sql)、
[筛选与验证汇总](../results/paper_official_predicates_20260930/validation_summary.json)。

## 早期候选与诊断记录

若要求 customer 不加过滤、orders/lineitem 各一个 unary predicate，且不引入额外数值阈值，
可使用 [承诺日当天收货的版本](tpch/fulfilled_orders_received_on_commit_date.sql)。
其 TPC-H 业务背景、正常 gate 决策及 SF1 复测见下文“不引入数值阈值的日期关系谓词”一节。

## 查询语义

为建筑行业中账户余额至少为 9000 的客户生成**已完成订单的行金额明细**，
同时保留没有符合条件订单明细的客户，订单号和行金额在这些记录中为 NULL。
`l_extendedprice` 为折扣前行金额；`o_orderstatus = 'F'` 表示订单所有行均已发货。
F 的含义可由本仓库的 [TPC-H dbgen](../../extension/tpch/dbgen/build.cpp) 中 `ocnt == o->lines` 的赋值确认。

这可以用作客户组合的订单覆盖情况报表：既查看已产生的明细，也保留尚无已完成订单的客户。
谓词均直接使用业务列，不使用 hash、取模、随机抽样或人为改写连接键。

```sql
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
) ON c_custkey = o_custkey
WHERE c_mktsegment = 'BUILDING'
  AND c_acctbal >= 9000;
```

[可直接运行的 SQL](tpch/building_customers_fulfilled_orders.sql)

相对最初的论文 SQL，这个实例替换的是 unary predicates：去掉 1995 年日期范围及 AIR 限制，
增加已完成订单、市场类别和余额范围条件。两条 join condition、LEFT/INNER 结构和 SELECT 列保持不变。
它是同类查询的一个新业务实例，不是声称与最初 SQL 返回相同数据。

## 算法如何选择

令 C 为过滤后的客户，O 为已完成订单，L 为明细。正常 DuckDB 先算 O ⋈ L，再连接 C。
OuterYan 按原有两轮 semi-join reduction 缩减 O 和 L，然后 DP 自然选择先连接 C–O，再连接 L。
实际物理计划可因 build/probe 方向显示 RIGHT JOIN，表分组确实为 `(customer, orders)` 先连接。

没有固定目标顺序、修改 DP 枚举、添加 join hint 或使用 `DUCKDB_OY_FORCE_CANDIDATE`。
调整前的 Release 对这个同样的 SQL 就已产生 `outer_reordered=1`；当时仅被最终 gate 拒绝。

为本次单例实验，将源码级 `SEMIJOIN_COST_RATIO` 从 1.0 改为 0.20。
同 grouping 回退、成本比较、保守场景和 1.20 门槛均保留。它是**全局实验权重**，不是 SQL 特判，
也不是经过全量工作负载校准的通用默认值。论文复现需要明确报告该参数。

合并去重前，按版本累计的独立 EXPLAIN 检查显示：权重 0.20、门槛 1.20 时，908 个实例中
553 个选择 OuterYan（60.90%）；先前权重 1.0 的 203/908 属于另一配置。
固定权重 0.20，仅回放门槛 1.25/1.30，可分别多接受 15/31 个候选，本例均仍通过。
这些是优化器选择统计及参数回放，不是全语料运行时间结果，也未改变下面实测的 1.20 门槛。
当前唯一查询集已重新 EXPLAIN：650 条中 399 条选择 OuterYan（61.38%），全部进入 DP。
上述 908 实例统计和门槛回放是历史口径，不应当作去重后的查询数量。
见[完整成本分布和参数分析](../results/semantic_gate_tuning_20260929/summary.md)。

实验配置下 ON 的真实决策：

```text
selection_mode=GATED
outer_reordered=1
cost_gate_applied=1
selected_plan=OUTERYAN
outer_yan_selected=1
gate_result=PASS
reason=COST_OUTERYAN_BETTER
semijoin_cost_ratio=0.2
```

| 模型成本项 | 数值 |
|---|---:|
| DuckDB baseline | 8,099,444.104 |
| DP 候选的真实 join 成本 | 1,147,030.442 |
| 原始 SJ 工作量 | 32,444,524 |
| 加权候选总成本 | 7,635,935.242 |
| 门槛：1.20 × baseline | 9,719,332.924 |

相同真实 join 成本和 SJ 工作量在权重 1.0 时总成本为 33,591,554.442，被 gate 拒绝。
因此权重调整改变的是最终接受决策，目标 grouping 的产生来自 DP 本身。

## SF1 实测

本地现有 TPC-H SF1：customer 150,000、orders 1,500,000、lineitem 6,001,215 行。
使用重新构建的 Release、10 线程，每模式 11 次正式样本。每模式分两批、各预热两次，第二批反转顺序。
裸 SELECT 完整消费结果，不包装 CTAS/COPY/LIMIT；计时关闭 trace/profile 和输出格式化，包含优化与结果消费。
profile 独立采集；计时时构建和测试进程已经结束。

| 指标 | OuterYan OFF | ON（实验权重 0.20） |
|---|---:|---:|
| 先连接的两表 | orders–lineitem | customer–orders |
| 第一个真实 join 的输出 | 2,901,744 | 14,319 |
| 两个真实 join 的输入行数之和 | 8,677,848 | 83,863 |
| SJ probe 数量 | 0 | 3 |
| 最终输出 | 54,293 | 54,293 |
| 耗时中位数 | 24.043 ms | 18.067 ms |
| OFF / ON | — | 1.331× |

ON/OFF 完整结果多重集一致，保留重复行。筛选后的客户有 2,762 个，其中 915 个没有匹配的已完成订单明细，
这些客户仍以 NULL 扩展行出现在结果中，说明 LEFT JOIN 的业务含义在这个数据上实际生效。
“真实 join 输入”不包含 SJ 工作量；上述耗时包含所有 SJ 构建、探测及物化工作。
这是单机 SF1 的单例结果，不是 SF100 性能或全量 benchmark 的结论。

构造过程中对 100 组具有业务含义的一元谓词组合做了计划筛选，记录保存在
[semantic_results.json](../results/paper_cost_tuning_20260929/semantic_results.json)。
最终余额与市场类别组合在计时前确定；11 个原始耗时样本全部保留。

## 保留当前参数，单独验证候选计划（2026-09-30）

本节及下一节的 `auto_test/results/` 链接指向本机实验产物，该目录按仓库规则不提交。
SQL 和测试入口随仓库保存；重新运行命令会生成带新时间戳的结果目录。

重新核对的本地源码与 Release decision trace 均为 SJ 权重 `0.20`、gate 上限 `1.20`，
原 BUILDING 实例仍正常通过 gate。本次没有修改任何优化器源码、参数、统计或 join condition。
若另一构建的 gate 拒绝该候选，可使用现有的进程级诊断模式：

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/building_customers_fulfilled_orders.sql \
  --threads 10 --runs 11 --force-candidate
```

此命令分别测 OFF、正常 ON 和 forced。脚本只在 forced 子进程设置
`DUCKDB_OY_FORCE_CANDIDATE=1`，不修改常量，也不将它传给正常 ON/OFF。
DP 仍按原算法产生候选；开关跳过最终 cost gate 和同 grouping 回退，不能保证任意 SQL 都改变 grouping。
本例应检查 `outer_reordered=1` 以及 profile 中的 customer–orders 分组。
forced 的原因是 `FORCE_OUTERYAN_DIAGNOSTIC`，论文应将其报告为候选计划执行实验，不能当作正常成本模型接受的证据。

### 调整 orders 日期范围的检查

检查了 12 个日期窗口（多年、年、半年、季度、月、周和单日范围），分别应用于：
保留 BUILDING + F 条件、用日期替代 F 条件、以及最初含 AIR 的 SQL，共 36 个变体及 1 个无日期对照。
同一家族内所有窗口的 DP / gate 决策及成本均相同：

| 条件家族 | DP 改变 grouping | 最终选择 | 候选 / baseline 成本 |
|---|---|---|---:|
| BUILDING + 高余额 + F + 日期范围 | 是 | OuterYan | 0.942773 |
| BUILDING + 高余额 + 日期范围（去掉 F） | 是 | DuckDB | 1.435469 |
| 原始 AIR 例子，仅改变日期范围 | 否 | DuckDB | 2.048085 |

当前 `RelationStatisticsHelper::InspectTableFilter` 对这些日期不等式不按区间宽度估计选择率：
只有日期范围时使用默认 20%；与 `o_orderstatus = 'F'` 并存时沿用等值估计，日期不会进一步降低该估计。
所以调整实际时间窗口会改变执行数据量，但这些窗口没有改变模型成本；不能依靠它绕过拒绝的 gate。
这不是对所有 SQL 谓词形式的穷尽结论。
参见[筛选决策](../results/paper_date_ranges_20260930_091300/results.json)和
[统计实现](../../src/optimizer/join_order/relation_statistics_helper.cpp)。

另存的 [1995 年版本](tpch/building_customers_fulfilled_orders_1995.sql) 只给 BUILDING 实例增加订单日期范围，
语义为“这些客户在 1995 年下单的已完成订单明细”。10 线程、每模式 11 次，完整结果均为 5,114 行，
ON 和 forced 的物理 profile 都确认先 customer–orders，且均包含三个 SJ probes。
OFF / ON / forced 中位数分别为 **7.696 / 17.330 / 17.015 ms**：这次日期收窄使重排更慢，
因此该变体只验证计划与正确性，不替代前述性能正例，也不能沿用前述 1.331× 加速结论。
原始数据见[结果](../results/paper_building_customers_fulfilled_orders_1995_20260930_091523/result.json)及
[物理 grouping 验证](../results/paper_building_customers_fulfilled_orders_1995_20260930_091523/verified_physical_groupings.json)。

## 只替换 lineitem 谓词并正常通过门控（2026-09-30）

对于最初的论文 SQL，保持 1995 年订单范围和两个连接条件，只将
`l_shipmode = 'AIR'` 替换成 `l_receiptdate > l_commitdate`，可以正常通过当前门控。
这个谓词只引用 lineitem，仍是一元过滤；业务含义为实际收货日晚于承诺日的订单行。
查询保留没有此类订单明细的客户。见[完整 SQL](tpch/customer_orders_late_receipts_1995.sql)。

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/customer_orders_late_receipts_1995.sql \
  --threads 10 --runs 11
```

没有使用 force、改变 join condition、修改 DP 或任何 cost 参数；使用现有权重 `0.20` 和上限 `1.20`。
本实例自然选中 customer–orders 先连接，并经真实执行 profile 验证。

| 模型项 | 数值 |
|---|---:|
| DuckDB baseline | 7,027,350.201 |
| 候选 real-join 成本 | 1,873,511.465 |
| 候选原始 SJ 工作量 | 31,386,419 |
| 候选总成本（SJ 权重 0.20） | 8,150,795.265 |
| 上限（baseline × 1.20） | 8,432,820.242 |
| 候选 / baseline | 1.159868 |

决策为 `selection_mode=GATED outer_reordered=1 cost_gate_applied=1 selected_plan=OUTERYAN`
及 `reason=COST_OUTERYAN_WITHIN_LIMIT`。模型估计候选成本高约 16%，因在现有 20% 容许范围内被接受，
不能将其表述为“模型认为候选成本更低”。当前模型对这个列间日期比较也没有精确选择率估计；
本例的成本与移除 lineitem 过滤的对照相同。

SF1、10 线程、各 11 次：OFF / ON 中位数为 **20.881 / 32.275 ms**，完整结果多重集一致，均为 641,926 行。
OFF 首个真实 join（orders–lineitem）输出 576,370 行，ON 首个真实 join（customer–orders）输出 275,041 行。
ON 包含三个 SJ probes；总耗时包括 SJ 工作。因此该例证明正常模型接受并执行重排，**没有证明性能收益**。

对三个固定的 customer/orders 条件家族分别测试了 16 个 lineitem 条件（包括无过滤对照），共 48 个 EXPLAIN。
其中“BUILDING + 高余额 + 日期，去掉 F”的 16 个变体仍全部被 gate 拒绝；
“BUILDING + 高余额 + F + 日期”本来就能通过，加入 `l_returnflag = 'R'` 等条件也能通过。
最初含 AIR 的查询则是 DP grouping 未变，不能与“DP 已改变但 gate 拒绝”的版本混淆。
这次谓词筛选不是所有一元谓词的穷尽证明。

证据：[谓词筛选及决策](../results/paper_lineitem_predicates_20260930_093251/results.json)、
[可复现筛选脚本](../results/paper_lineitem_predicates_20260930_093251/search.py)、
[完整实测结果](../results/paper_customer_orders_late_receipts_1995_20260930_093320/result.json)、
[物理 grouping 验证](../results/paper_customer_orders_late_receipts_1995_20260930_093320/verified_physical_groupings.json)。

## 只调整 orders / lineitem，正常选择且实测更快（2026-09-30）

新例子不对 customer 添加过滤，仅更换 orders 和 lineitem 的一元谓词。
相对原始 SQL，订单日期范围替换为 `o_orderstatus = 'F'`，AIR 条件替换为延期收货、数量与折扣条件。
两个 join condition、LEFT/INNER 结构、输出列和现有成本参数均不变。

业务含义：审查已完成订单中数量至少 25、折扣至少 5%、收货日晚于承诺日的明细，
同时保留没有此类明细的客户。

```sql
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_receiptdate > l_commitdate
       AND l_quantity >= 25
       AND l_discount >= 0.05
) ON c_custkey = o_custkey;
```

[可运行 SQL](tpch/fulfilled_orders_late_discounted_lines.sql)，测试命令：

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/fulfilled_orders_late_discounted_lines.sql \
  --threads 10 --runs 11
```

正常 ON 的 DP 选择 customer–orders 先连接，cost gate 接受，实际 profile 也确认该顺序及三个 SJ probes。
没有使用 force、join hint、统计注入、hash/modulo 谓词或额外的 customer 条件。
现有参数仍为 SJ 权重 `0.20`、gate 上限 `1.20`。
候选总成本 `2,776,560.151` / baseline `2,472,852.934` = **1.122817**，低于上限；
原因是 `COST_OUTERYAN_WITHIN_LIMIT`，并非模型估计候选更便宜。

固定此查询后，两轮独立 SF1 验证均使用相同 Release、10 线程，每轮 OFF/ON 各 11 个正式样本。
每轮均比较裸 SELECT 的完整多重集，均为 **573,766 行**；每模式分两批，每批预热两次，第二批反转模式顺序。
计时包含优化、所有 SJ 和结果消费，关闭 trace/profile；不删任何正式样本。

| 独立验证 | OFF 中位数 | ON 中位数 | OFF / ON |
|---|---:|---:|---:|
| 第一轮 | 45.615 ms | 37.362 ms | 1.221× |
| 第二轮 | 45.538 ms | 36.442 ms | 1.250× |

相比前述仅有“晚收货”的慢例子，本例 ON 第一轮 SJ 构建处理约 **107.6 万**条 lineitem，
而非约 379.3 万；orders 从 **729,413** 行减少到 **369,177** 行，减少约 49.4%，
而慢例子的 orders 只减少约 8.4%。本例两个真实 join 输入行数之和从 **2,475,068** 降为 **1,462,120**。
这些 profile 计数说明额外数量和折扣条件降低了 SJ 工作量、增强了 orders 约简；
实际总耗时的两轮复测才是收益证据，不能仅凭这些行数推广到其他查询或 scale。

构造过程对同一三表查询的 219 个 orders/lineitem 业务条件组合做了 EXPLAIN，96 个正常接受新 grouping。
第一轮探索计时每模式各两次，用于筛选；反序第二轮 ON 在另一候选（全时间范围、无 lineitem 过滤）处
发生 INTERRUPT，未计为完成，原始日志保留。上表来自固定本 SQL 后重新运行的两轮完整独立验证，
不混用探索样本；完整验证的所有正式样本均保留。

本机原始产物（`auto_test/results/` 按仓库规则不提交）：

- [筛选与验证记录](../results/paper_orders_lineitem_search_20260930/validation_summary.json)
- [全部 219 个优化器决策](../results/paper_orders_lineitem_search_20260930/decisions.json)
- [第一轮完整结果及样本](../results/paper_candidate_89_fulfilled_late_large_discounted_20260930_095607/result.json)
- [第二轮完整结果及样本](../results/paper_fulfilled_orders_late_discounted_lines_20260930_095647/result.json)
- [第二轮物理 grouping 验证](../results/paper_fulfilled_orders_late_discounted_lines_20260930_095647/verified_physical_groupings.json)

## lineitem 仅一个谓词的正例（2026-09-30）

保持上一例的 `o_orderstatus = 'F'`，将 lineitem 的三个条件替换为单个条件：

```sql
AND l_quantity >= 50
```

业务含义变为“已完成订单中数量至少 50 的明细”，仍保留所有 customer。
这是业务筛选的替换，不是把原来延期、数量、折扣三项限制等价合并；新旧查询的结果不同。
见[完整 SQL](tpch/fulfilled_orders_large_quantity_lines.sql)。

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/fulfilled_orders_large_quantity_lines.sql \
  --threads 10 --runs 11
```

现有参数保持 `0.20 / 1.20`，不使用 force。正常 ON 的 DP 选出 customer–orders 先连接，
成本比仍为 `1.122817`，由 `COST_OUTERYAN_WITHIN_LIMIT` 接受；两轮物理 profile 均确认该顺序。
SF1、10 线程，每轮每模式各 11 次，完整结果多重集均一致，**166,329 行**。

| 独立验证 | OFF 中位数 | ON 中位数 | OFF / ON |
|---|---:|---:|---:|
| 第一轮 | 24.304 ms | 20.078 ms | 1.210× |
| 第二轮 | 26.140 ms | 22.994 ms | 1.137× |

两轮使用相同二进制，所有正式样本均保留。ON 的 SJ 构建处理 **119,846** 条 lineitem，
orders 从 **729,413** 行约简到 **55,670** 行；真实 join 输入行数之和约从 105 万降至 42.8 万。
查询输出中仍有匹配的订单行，不能将其视为没有匹配数据的空连接特例。

此次先筛选 20 个有业务含义的单一比较条件，再固定本 SQL 做两轮完整验证。
本机原始产物（不随仓库提交）：[筛选及验证汇总](../results/paper_single_lineitem_predicate_20260930/validation_summary.json)、
[探索计时](../results/paper_single_lineitem_predicate_20260930/screening.json)、
[第一轮](../results/paper_fulfilled_orders_large_quantity_lines_20260930_110119/result.json)、
[第二轮](../results/paper_fulfilled_orders_large_quantity_lines_20260930_110134/result.json)、
[第二轮物理 grouping](../results/paper_fulfilled_orders_large_quantity_lines_20260930_110134/verified_physical_groupings.json)。

## 不引入数值阈值的日期关系谓词（2026-09-30）

[标准 TPC-H Q21](../../extension/tpch/dbgen/queries/q21.sql) 同时使用
`o_orderstatus = 'F'` 与 `l_receiptdate > l_commitdate`，关注已完成订单中的延期收货明细。
沿用这种业务列之间的比较，本例将关系改为：

```sql
AND o_orderstatus = 'F'
AND l_receiptdate = l_commitdate
```

含义是已完成订单中**恰好在承诺日当天收货**的明细，并保留无匹配明细的客户。
这里特指当天，提前收货不符合条件；不能将它解释为更宽泛的“承诺日之前或当天收货”。
这是 Q21 交付日期比较的业务变体，不是原 Q21 谓词原样复用，也不是标准 Q21 查询。
orders 和 lineitem 各只有一个 unary predicate，不添加数量、金额或延迟天数阈值。
两个连接键及外连接结构保持不变。

[完整 SQL](tpch/fulfilled_orders_received_on_commit_date.sql)：

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/fulfilled_orders_received_on_commit_date.sql \
  --threads 10 --runs 11
```

参数仍为 SJ 权重 `0.20`、gate 上限 `1.20`，无 force 或统计注入。
DP 自然选择 customer–orders 先连接，实际物理 grouping 也已验证。
候选总成本 `10,423,559.210` / baseline `12,204,911.882` = **0.854046**，
正常接受原因是 `COST_OUTERYAN_BETTER`。

两轮独立 SF1 验证均使用 10 线程，每模式 11 次正式样本，裸查询完整多重集一致，共 **153,318 行**。
第一轮 OFF / ON 为 **21.492 / 17.923 ms（1.199×）**，第二轮为 **19.588 / 19.116 ms（1.025×）**。
由于收益幅度有波动，追加 32 对相邻 OFF/ON 交替计时：共用已预热连接，每模式先预热三次，
每对反转先后顺序，SET 不计时，SELECT 完整消费结果，trace/profile 关闭，保留全部正式样本。
该次 OFF / ON 中位数为 **20.960 / 18.075 ms（1.160×）**，32 对中有 31 对 ON 更快。
不能只引用第一轮 1.199× 而忽略第二轮的小幅收益；额外交替实验与原两轮的计时安排不同，应分别报告。

ON 的 SJ 构建处理 **49,736** 条 lineitem，orders 从 **729,413** 行减至 **23,844** 行。
最终有 **24,275** 条匹配明细，外连接继续保留没有此类明细的客户；并非空连接特例。
这些是本机 SF1 证据，不推广为标准 Q21 或其他 scale 的性能结论。

此次检查了 8 个日期关系或 TPC-H 类别谓词；原样使用 Q21 的延期比较，以及 `l_returnflag = 'R'`，
在本三表例子的探索计时中均没有收益。上述加速对应的是明确标注的“承诺日当天收货”变体。

本机原始产物（不随仓库提交）：[筛选及验证汇总](../results/paper_tpch_semantic_predicate_20260930/validation_summary.json)、
[第一轮](../results/paper_fulfilled_orders_received_on_commit_date_20260930_110737/result.json)、
[第二轮](../results/paper_fulfilled_orders_received_on_commit_date_20260930_110758/result.json)、
[物理 grouping](../results/paper_fulfilled_orders_received_on_commit_date_20260930_110758/verified_physical_groupings.json)、
[32 对交替计时与全部样本](../results/paper_tpch_semantic_predicate_20260930/paired_timing.json)、
[可直接在 CLI 回放的交替脚本](../results/paper_tpch_semantic_predicate_20260930/paired_timing.sql)。

## orders 也使用单一时间谓词（2026-09-30）

`o_orderstatus = 'F'` 表示该订单所有明细行均已发货；这是发货进度条件。
仓库 [dbgen](../../extension/tpch/dbgen/build.cpp) 在已发货明细数等于订单总明细数时设置 F。
如果希望改为下单时间条件，可以直接借用 [TPC-H Q3](../../extension/tpch/dbgen/queries/q03.sql) 的：

```sql
AND o_orderdate < DATE '1995-03-15'
```

日期是 Q3 中的报告截止日，而非本次为收益搜索出来的日期。
将它与 `l_receiptdate = l_commitdate` 配合，得到“截止日前下单、且恰好在承诺日当天收货”的明细，
同时保留无匹配明细的客户。orders 与 lineitem 仍各一个 unary predicate。
下单时间条件与 F 状态条件含义不同，替换后不要求所有明细均已发货，也不与 F 版本结果等价。
本三表外连接查询仍是业务变体，不是标准 Q3。

[完整 SQL](tpch/orders_before_cutoff_received_on_commit_date.sql)：

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/orders_before_cutoff_received_on_commit_date.sql \
  --threads 10 --runs 11
```

当前参数 `0.20 / 1.20` 保持不变，正常 ON 由 DP 选中 customer–orders，物理 profile 也确认该顺序。
成本比 `1.159868`，通过 gate，原因为 `COST_OUTERYAN_WITHIN_LIMIT`。
SF1、10 线程、各 11 次，本次中位数 OFF / ON 为 **20.320 / 17.831 ms（1.140×）**。
裸 SELECT 完整结果多重集一致，共 **153,302 行**，无 force。
本机原始数据：[结果与全部样本](../results/paper_orders_before_cutoff_received_on_commit_date_20260930_111402/result.json)、
[物理 grouping](../results/paper_orders_before_cutoff_received_on_commit_date_20260930_111402/verified_physical_groupings.json)。

## 增加一个有业务含义的 lineitem 条件，及更宽的 orders 截止日（2026-09-30）

首先固定 `o_orderdate < DATE '1995-03-15'` 和 `l_receiptdate = l_commitdate`，
仅追加一个 lineitem 谓词。退货标记、运输方式、折扣/免税等普通条件未能通过当前 gate；
折扣率与税率比较、含税折后金额与原价比较、跨月/季度/年份运输等关系条件仍可正常选择新计划。
但同一连接中轮换四个查询、各 32 对 OFF/ON 的交替对照，没有显示追加条件带来明显额外收益：
无新增条件为 1.204×、`l_discount > l_tax` 为 1.199×、跨年条件为 1.211×。
所以不能把不同时间测试所得的微小比值差异报告成新增谓词的收益。

继续在此前允许调整的 orders 时间范围内检查年度截止日，保留一个 orders 条件及两个 lineitem 条件，
得到[跨年交付审计版本](tpch/orders_before_1997_cross_year_on_commit_date.sql)：

```sql
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate = l_commitdate
       AND EXTRACT(YEAR FROM l_shipdate) < EXTRACT(YEAR FROM l_receiptdate)
) ON c_custkey = o_custkey;
```

业务含义：审查 1997 年前下单、运输跨越日历年、且恰好在承诺日当天收货的明细，
保留无匹配明细的客户。这里限定的是下单截止日，不是声称收货也必须发生在截止日前。
新增条件只有一个日期关系比较，没有额外数量/金额阈值；年份提取是 TPC-H Q7/Q8 也使用的表达方式，
但本跨年筛选不是声称直接来自某条标准 TPC-H 查询。

```bash
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/orders_before_1997_cross_year_on_commit_date.sql \
  --threads 10 --runs 11
```

保持成本参数 `0.20 / 1.20`，无 force、统计注入、customer 过滤或 join condition 修改。
DP 正常选中 customer–orders 先连接，成本比 `1.159868`，通过 gate；物理 profile 确认该顺序和三个 SJ probes。
SF1、10 线程、每模式 11 次，OFF / ON 中位数 **29.596 / 19.261 ms（1.537×）**。
裸 SELECT 完整结果多重集一致，**150,017 行**，其中 1,541 条匹配明细，148,476 条为无匹配客户的 NULL 扩展行。
这是稀疏匹配的外连接实例，应明确报告该数据分布。

为分离截止日变化和新增谓词的效果，再在同一连接中轮换三种固定查询，
各执行 32 对相邻 OFF/ON，交替先后顺序，SET 不计时，trace/profile 关闭，保留所有样本：

| 版本 | OFF 中位数 | ON 中位数 | OFF / ON |
|---|---:|---:|---:|
| 原截止日 1995-03-15，无新增条件 | 21.043 ms | 18.790 ms | 1.120× |
| 截止日 1997-01-01，无新增条件 | 27.460 ms | 19.246 ms | 1.427× |
| 截止日 1997-01-01，加跨年条件 | 28.619 ms | 20.266 ms | 1.412× |

跨年版本的 32 对中 ON 均更快。但更大的加速主要与截止日变化相关，
**没有证据表明新增跨年谓词本身提高了加速比**；如果必须固定旧截止日，当前搜索未找到明显更强的新增谓词。
ON 的 SJ 将 orders 从 **1,138,594** 行缩减到 **1,537** 行，真实 join 输入合计从 **1,291,987** 降为 **303,091**。
这些是该实例的实测数据，不意味着截止日越晚越好，也不推广为其他 scale 的保证。

本机原始产物（不随仓库提交）：[筛选与验证摘要](../results/paper_extra_lineitem_predicate_20260930/validation_summary.json)、
[固定旧截止日的交替比较](../results/paper_extra_lineitem_predicate_20260930/balanced_comparison.json)、
[年度截止日对照与全部交替样本](../results/paper_extra_lineitem_predicate_20260930/annual_balanced_comparison.json)、
[独立 11 次验证](../results/paper_orders_before_1997_cross_year_on_commit_date_20260930_113328/result.json)、
[物理 grouping](../results/paper_orders_before_1997_cross_year_on_commit_date_20260930_113328/verified_physical_groupings.json)。

## 必要的执行修复与验证

候选此前会因列裁剪使 SJ 的预解析列位置失效而越界。现在在 RemoveUnusedColumns 和 ColumnLifetimeAnalyzer 中，
保留 SJ 输入的现有 schema，避免 key 索引失效；没有禁用整个列裁剪优化器，也没有修改 pipeline 依赖或 SJ 阶段。
代价是 SJ 输入下方可能保留额外列，后续若改为可追踪的 key binding 可以进一步优化。

- 旧二进制在新增的小规模回归数据上复现越界，新二进制通过；覆盖 scan filter、局部 residual filter 和 verification。
- 191 个非 slow 的 OuterYan 用例通过，共 5,431 个断言。
- bitmap budget 用例通过，共 127 个断言。
- 全部 `[outer_yan]` 的运行在 TPC-DS SF0.1 慢测处耗时较长，被主动停止；不能报告完整慢测套件通过。
- 本实例另外验证了 EXPLAIN / 裸 SELECT 的决策一致，及 profile 中真实物理 grouping 和三个 SJ probes。

## 复现与原始数据

```bash
ninja -C build/release -j 4 duckdb unittest
python3 auto_test/paper_examples/run_example.py \
  --query auto_test/paper_examples/tpch/building_customers_fulfilled_orders.sql \
  --threads 10 --runs 11
```

确认源码 `SEMIJOIN_COST_RATIO=0.20`，不设置 force 环境变量。
OFF 使用 `disabled_optimizers='outer_yan'`，ON 使用空列表。无需构造或加载额外测试数据。

- [完整结果与二进制 SHA-256](../results/paper_building_customers_fulfilled_orders_20260929_180342/result.json)
- [汇总 CSV](../results/paper_building_customers_fulfilled_orders_20260929_180342/summary.csv)
- [全部耗时样本 CSV](../results/paper_building_customers_fulfilled_orders_20260929_180342/timing_samples.csv)
- [查询完整结果 CSV](../results/paper_building_customers_fulfilled_orders_20260929_180342/query_result.csv)（NULL 标记为 `__SQL_NULL__`）
- [ON 最终计划](../results/paper_building_customers_fulfilled_orders_20260929_180342/on.plan.txt)
- [ON 裸查询决策 trace](../results/paper_building_customers_fulfilled_orders_20260929_180342/on.correctness.trace.txt)
- [物理 grouping 验证](../results/paper_building_customers_fulfilled_orders_20260929_180342/verified_physical_groupings.json)
- [调整前相同 SQL 的 DP / gate 决策](../results/paper_building_customers_fulfilled_orders_20260929_180342/before_weight_change.trace.txt)

可用于论文的简短表述：

> 本例检索建筑行业高余额客户的已完成订单明细，并保留没有匹配订单的客户。
> OuterYan 的半连接约简使 DP 选择先连接 customer 与 orders，将首个真实连接的输出从 2.90M 行降至 14.3K 行。
> 在 SJ 相对成本权重为 0.20 的实验配置下，该候选通过正常成本门控；SF1 上完整查询中位耗时由 24.04 ms 降至 18.07 ms，约加速 1.33 倍。
