# 有业务语义、由 DP 自然选中的三表重排例子

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
