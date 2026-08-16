# 腾讯云大数据 AI-Native Data Infra 与流湖一体岗位准备

## 综合文献综述、能力映射与面试问答

- 适用课题一：腾讯云大数据 - AI Native Data Infra 平台关键技术研究
- 适用课题二：腾讯云大数据 - 流湖一体统一增量计算引擎关键技术研究
- 候选人背景：查询求值与查询优化，Yannakakis+，运行时过滤器，以及内存、CPU、I/O 瓶颈优化
- 更新日期：2026-08-10

> 本文以数据库系统研究视角组织，而不是把岗位描述拆成孤立知识点。核心目标是帮助候选人建立一条可用于简历、技术面试和系统设计面试的统一叙事：先减少无效数据和昂贵工作，再选择正确的执行位置、数据布局与资源调度方式，最后用可验证的代价模型闭环。

---

## 0. 如何使用本文

面试准备建议分三遍完成：

1. 第一遍只读第 1、2、6 节，形成岗位判断和自我介绍。
2. 第二遍精读第 3、4、5 节，能用自己的话解释系统机制和论文脉络。
3. 第三遍使用第 7 节进行限时口述，并按照第 8 节补读原始论文。

回答系统问题时，始终使用同一结构：

1. 明确语义与正确性约束。
2. 描述逻辑计划和物理执行路径。
3. 给出 CPU、内存、I/O、网络、GPU 或推理成本模型。
4. 说明自适应机制与降级路径。
5. 给出指标、基线、消融实验和故障场景。

---

## 1. 执行摘要

### 1.1 岗位匹配结论

| 维度 | AI-Native Data Infra | 流湖一体 Setats | 你的现有匹配度 |
|---|---|---|---|
| 查询优化与执行 | AI 算子、SQL+LLM、跨 CPU/GPU 计划 | 流、增量、批统一计划，向量化算子 | 强 |
| 运行时过滤 | 在调用 LLM/GPU 前裁剪输入 | 在远程扫描、点查、Join 前裁剪数据 | 很强 |
| 代价模型 | 延迟、费用、质量、GPU 时间的多目标优化 | 读放大、写放大、缓存、压缩、远程 I/O | 强，可迁移 |
| 存储系统 | 向量索引、多模态对象、缓存 | LSM、Deletion Vector、列存、缓存与预取 | 需要重点补齐后者 |
| 工程栈 | Python/C++、GPU、推理服务 | 现代 C++、异步 I/O、Flink/湖格式 | 第二岗更强调 C++ 深度 |
| 研究叙事 | 把 LLM/Embedding 当作昂贵且有质量维度的算子 | 把半连接削减扩展到远程存储和增量状态 | 两岗均可形成差异化 |

直接匹配度上，第二个岗位更贴近你已有的查询求值、Yannakakis+ 和运行时过滤工作；第一个岗位则提供更大的研究迁移空间。你在第一岗的差异化不应被表达为“我也会调用大模型”，而应是：

> 我研究如何在正确性约束下，通过查询重写、运行时统计和资源感知执行，减少昂贵算子的输入。对传统 Join，这个昂贵工作是无效扫描、哈希构建和中间结果；对 AI-Native 查询，它可以是 Embedding、LLM 调用、GPU 内核和 KV cache 占用。两者共享选择率估计、代价建模、算子下推、结果复用和自适应执行问题。

### 1.2 推荐的 30 秒自我介绍

> 我的研究主要是查询求值和查询优化，重点关注 Yannakakis 类半连接削减、Join 重排和运行时过滤。我也做过运行时过滤器优化，会根据负载判断系统是 CPU、内存还是 I/O 受限，并在过滤器构建、传递和消费路径上做取舍。这个经验和 Setats 的远程 I/O 裁剪、向量化执行及增量状态管理直接相关；对 AI-Native Data Infra，我希望把同一套思想扩展到 LLM、Embedding 和 GPU 算子，用代价、延迟和质量联合模型决定下推、批处理、缓存和路由策略。

不要在自我介绍里虚构吞吐量或加速比。把你真实实验中的数据替换到以下槽位：

- 数据规模：`[行数 / 字节数 / 查询数]`
- 对照基线：`[无过滤 / 原生优化器 / 另一种过滤器]`
- 核心结果：`[端到端延迟、扫描字节、CPU cycles、峰值内存]`
- 最差场景：`[高选择率、基数误估、过滤器迟到、内存预算不足]`

---

## 2. 两个岗位的统一技术地图

```text
SQL / Agent Intent
        |
        v
Logical optimization
  join graph, predicate transfer, semantic operators, incremental rewrites
        |
        v
Cost and quality model
  cardinality, selectivity, bytes, CPU, memory, network, GPU, tokens, quality
        |
        v
Physical planning
  scan pruning, runtime filters, vectorized kernels, CPU/GPU placement,
  cache/prefetch, LLM batching/routing, stream/incremental/batch mode
        |
        v
Adaptive execution and scheduling
  late statistics, backpressure, autoscaling, admission control, fallback
        |
        v
Verification
  result semantics, exactly-once, quality constraints, lineage, benchmarks
```

两岗共同考察的不是“记住多少系统名”，而是能否跨层推理：

- 优化器下推一个过滤器后，存储层能否真正减少远程 Range GET？
- GPU 内核快十倍，但排队和 Host-to-Device 拷贝后是否仍然获益？
- LLM 结果可缓存，但 Prompt、模型版本、数据快照或权限变化后是否仍然等价？
- 增量模式减少重算，但状态、乱序、撤回流和 Checkpoint 是否抵消收益？
- 向量化提高 CPU 效率，但批大小是否增加尾延迟或内存压力？

---

## 3. 共同基础：从 Yannakakis 到运行时过滤与向量化执行

### 3.1 Yannakakis 算法为什么仍然重要

[Yannakakis 1981](https://www.sigmod.org/publications/dblp/db/conf/vldb/Yannakakis81.html) 给出了无环连接查询的经典求值方法。对于一个 Join Tree，可先做自底向上的半连接削减，再做自顶向下削减，移除无法出现在最终结果中的元组，最后执行 Join。其意义并不只是复杂度结论，而是一个持续影响现代系统的设计原则：

> 尽可能在生成大中间结果之前传播“存在性”信息，并把无效元组在更靠近数据源的位置删除。

你应能解释以下四点：

1. **无环性**：关系超图存在 Join Tree，运行交集性质成立。
2. **两轮削减**：第一轮和第二轮具有方向与依赖，不能随意并发或合并。
3. **全约简**：在适用条件下，削减后的每个元组都能参与最终结果。
4. **物化与过滤**：理论上的精确半连接在工程中可以近似为 Bloom Filter、值集、范围或分区过滤。

现代工作把该思想推广到更一般的 Join Graph。[Free Join](https://arxiv.org/abs/2301.10841) 试图统一传统二元 Join 和 Worst-Case Optimal Join 的执行空间；[Predicate Transfer](https://www.vldb.org/cidrdb/papers/2024/p22-yang.pdf) 使用过滤信息在关系间传播以减少中间数据；[Robust Predicate Transfer](https://arxiv.org/abs/2502.15181) 进一步关注代价和鲁棒性；[Including Bloom Filters in Bottom-up Optimization](https://arxiv.org/abs/2505.02994) 则强调在优化阶段显式考虑 Bloom Filter，而不是把它当作执行器的附加技巧。

面试中需要主动指出：理论上的“线性复杂度”不等于实际最快。真实代价还包括：

- 额外扫描轮次和缓存污染。
- 过滤器构建、序列化、网络广播与同步等待。
- Bloom 假阳性带来的残余工作。
- 过滤器到达过晚，消费者已经完成大部分扫描。
- 高选择率时几乎无裁剪收益。
- Outer Join、NULL 和重复值语义对传播方向的限制。

### 3.2 半连接与运行时过滤器的关系

精确半连接要求判断某个 Key 是否存在于另一侧。运行时过滤器通常保存 Build Side Key 的近似摘要，再下推到 Probe Side Scan。常见形式如下：

| 过滤器 | 优点 | 局限 | 适用场景 |
|---|---|---|---|
| Min/Max | 极小、构建便宜、易下推到文件统计 | 对稀疏或多峰分布弱 | 有序键、分区、Row Group |
| In-list / Hash Set | 精确、点查强 | 高基数时内存大 | 小维表、低 NDV |
| Bloom Filter | 空间可控、无假阴性 | 有假阳性、哈希有 CPU 成本 | 中高 NDV、远程扫描 |
| Bitset / Bitmap | 探测快、可 SIMD | 依赖紧凑值域，预算可能爆炸 | 稠密整数键 |
| 分区过滤器 | 可直接跳过文件或分区 | 粒度较粗 | Lakehouse、分布式 Exchange |

Bloom Filter 的近似假阳性率为：

```text
p ~= (1 - exp(-k * n / m))^k
k_opt = (m / n) * ln(2)
m / n = -ln(p) / (ln(2)^2)
```

其中 `m` 是位数，`n` 是插入元素数，`k` 是哈希函数个数。面试不能只背公式，还要给出预算策略：

- 先估计 Build Side NDV，而不是直接使用行数。
- 在给定内存预算下选择位数和哈希数。
- 若 NDV 超预算，可退化为更粗的分区或 Min/Max 过滤。
- 监控实际命中率和假阳性率，收益不足时停止构建或传播。
- 多个消费者共享过滤器时，构建成本可摊销，但要计入广播成本。

一个更完整的启用条件是：

```text
ExpectedBenefit
  = avoided_remote_bytes * io_cost_per_byte
  + avoided_rows * downstream_cpu_cost
  + avoided_network_bytes * network_cost_per_byte
  + avoided_expensive_ops * op_cost

ExpectedCost
  = build_cpu + build_memory + serialization + broadcast
  + consumer_probe_cpu + synchronization_delay

Enable if ExpectedBenefit > ExpectedCost + uncertainty_margin
```

这套模型可直接迁移到两个岗位：Setats 中 `expensive_ops` 是远程读取、解压、反序列化、Join 与状态访问；AI-Native 中它可以是 Embedding、LLM Token、GPU Kernel 与向量检索。

### 3.3 正确性边界：Outer Join 与 NULL

运行时过滤器首先是语义问题，其次才是性能问题。

- 对 `L INNER JOIN R`，两侧都可基于对方 Key 做存在性裁剪，但要遵循构建依赖。
- 对 `L LEFT JOIN R`，可以用 L 的 Key 过滤非保留侧 R；不能用 R 的 Key 删除保留侧 L，否则会丢失本应 NULL 扩展的行。
- 对 `L RIGHT JOIN R`，方向相反。
- 对 `FULL OUTER JOIN`，通常不能用一侧存在性直接删除另一侧输入。
- `NULL` 是否参与匹配取决于谓词是普通等值、`IS NOT DISTINCT FROM`，还是更复杂表达式。
- 优化器交换 Join 子节点时，LEFT 和 RIGHT 的语义方向必须同时翻转。

面试时应说清楚：Bloom Filter 的假阳性只损失性能，不损失正确性；假阴性会错误删除结果，必须通过构建完成屏障、版本一致性和发布协议避免。

### 3.4 CPU、内存、I/O 受限时，优化目标不同

**CPU 受限**时：

- 减少哈希次数、分支误预测、虚函数和逐元组解释开销。
- 使用向量化批处理、SIMD、紧凑数据结构和算子融合。
- 让过滤器探测本身足够便宜，避免为了少量裁剪增加更多 cycles。

**内存受限**时：

- 控制过滤器、Hash Table、状态和中间 Chunk 的峰值。
- 使用预算化 Bloom/Bitmap、分区构建、Spill 和背压。
- 考虑内存带宽、NUMA 和 Cache Locality，而不只是分配字节数。

**I/O 或网络受限**时：

- 优先做列裁剪、分区裁剪、Row Group 跳过和运行时过滤下推。
- 合并小 Range GET、异步并发读取，并用预取隐藏 RTT。
- 指标使用“远程读取字节”和“请求数”，不能只看算子 CPU 时间。

诊断流程建议：

1. 先看 Wall Time 分解和硬件计数器，确认主瓶颈。
2. 对照扫描字节、行数、IPC、LLC Miss、内存带宽、I/O Queue Depth。
3. 单独测过滤器 Build、Probe、传播和等待时间。
4. 用选择率、NDV、数据倾斜、到达时间、内存预算做参数化实验。
5. 报告端到端结果，避免只展示微基准加速。

### 3.5 向量化与并行执行文献脉络

[MonetDB/X100](https://www.cidrdb.org/cidr2005/papers/P19.pdf) 说明以向量为单位执行可以在函数调用开销、缓存局部性和编译器优化之间取得平衡。[Morsel-Driven Parallelism](https://www-db.in.tum.de/~leis/papers/morsels.pdf) 用小任务块进行动态调度，以处理核间负载均衡和数据倾斜。[Velox](https://vldb.org/pvldb/vol15/p3372-pedreira.pdf) 展示了可复用向量化执行引擎的工程设计。[DuckDB](https://duckdb.org/library/embedded-analytics/) 则是理解 DataChunk、Pipeline 和 Push-Based 执行的实用入口。

面试时应能说明批大小的取舍：

- 太小：调度、函数调用和边界检查开销高。
- 太大：缓存不友好、峰值内存高、过滤器或取消信号响应慢、尾延迟增加。
- 最优值与列宽、算子类型、压缩格式、SIMD 宽度和并发度有关，应通过端到端实验选择。

[Join Order Benchmark](https://vldb.org/pvldb/vol9/p204-leis.pdf) 的重要结论是：基数估计错误会放大到 Join 顺序和物理算法选择；但一个鲁棒执行器和较好的成本关系也能缓解估计误差。对你的研究叙事而言，这意味着运行时过滤器不只是一个 Kernel，还可以成为优化器估计失败后的自适应修正机制。

---

## 4. 岗位一：AI-Native Data Infra 文献综述

### 4.1 把 AI 调用视为一等查询算子

传统 SQL 算子的输出通常具有确定语义，成本主要由行数、字节数和 CPU/I/O 决定。AI 算子具有新的维度：

- 成本受输入与输出 Token 长度、Batch Size、模型和硬件影响。
- 输出可能非确定，且质量与成本存在 Pareto 权衡。
- 服务可能有速率限制、排队、冷启动和外部失败。
- Prompt、模型版本、采样参数、RAG 上下文变化都会影响等价性。
- 多模态数据还涉及解码、预处理与 Host-to-Device 数据路径。

[Raven](https://arxiv.org/abs/1911.00231) 是较早探索关系数据库与深度模型推理优化的工作。[LOTUS](https://arxiv.org/abs/2407.11418) 将语义过滤、语义 Join 等作为声明式算子，并关注跨算子优化。[Palimpzest](https://arxiv.org/abs/2405.14696) 探索对非结构化数据管道进行代价与质量感知优化。较新的 [Sema](https://arxiv.org/abs/2603.11622) 和 [Larch](https://arxiv.org/abs/2606.07923) 可作为前沿预印本阅读，但面试时应明确它们是新近研究，不把尚未广泛验证的结论当作行业定论。

可以把语义算子建模为：

```text
SemanticFilter(input, prompt, model, quality_requirement)
SemanticMap(input, prompt, schema)
SemanticJoin(left, right, matching_instruction)
Embedding(input, model)
VectorSearch(query_embedding, index, k, recall_requirement)
```

优化机会包括：

1. 先执行便宜且高选择率的 SQL 谓词，再调用 LLM。
2. 使用小模型、规则或 Embedding 做级联预筛，难例再交给大模型。
3. 对共享前缀或相同输入批处理，提高 GPU 利用率。
4. 对重复输入做语义安全的结果复用。
5. 根据质量约束选择模型、Prompt、检索深度和重试策略。
6. 把 AI 算子选择率反馈给后续 Join 顺序与资源规划。

### 4.2 AI 算子的多目标代价模型

推荐在面试中写出一个约束优化模型：

```text
C(plan) = lambda_l * latency_p95
        + lambda_m * monetary_cost
        + lambda_g * gpu_time
        + lambda_q * quality_loss

subject to:
  quality(plan) >= Q_min
  latency_p99(plan) <= SLO
  memory(plan) <= budget
```

输入特征至少应包含：

- 传统特征：行数、NDV、选择率、列宽、数据位置。
- AI 特征：输入/输出 Token 长度分布、模型版本、Batch 延迟曲线。
- 系统特征：GPU 类型、队列长度、KV cache 占用、CPU-GPU 传输。
- 复用特征：结果缓存命中率、共享 Prompt 前缀长度、数据快照版本。
- 质量特征：模型准确率、置信度、路由器误差和任务风险级别。

静态估计很难准确，因此系统应支持在线校准：先对小样本执行，估计 AI 选择率和 Token 分布，再决定是否切换模型、改变批大小或停止昂贵计划。这与运行时过滤中的“先观察 Build Side NDV 和过滤效果，再选择 Bloom 大小或禁用过滤”是同一类思想。

### 4.3 SQL+LLM 的缓存、复用和增量推理

至少要区分三类缓存：

1. **精确结果缓存**：Key 应包括规范化 Prompt、输入内容或数据快照、模型与版本、系统 Prompt、采样参数、RAG/工具版本、租户和权限边界。
2. **Prefix/KV Cache**：自回归模型的 KV 状态只对相同前缀安全复用。Prompt 中间变化通常会使其后的因果状态失效，而不是只重算变化 Token。
3. **算子或中间结果缓存**：缓存 Embedding、分类结果、语义 Join 候选集，并根据输入增删做增量维护。

失效策略必须回答：

- 数据发生 Update 时，是按行、分区还是整个快照失效？
- 模型权重、Tokenizer、Prompt Template 或 RAG Corpus 变化时如何版本化？
- 非确定采样是否允许复用？若允许，语义契约是什么？
- 不同租户和权限是否可能通过缓存泄漏数据？
- 结果是否需要可审计的 Lineage 与过期时间？

相关系统工作构成一条清晰脉络：

- [Orca](https://www.usenix.org/conference/osdi22/presentation/yu)：迭代级调度与连续批处理思想。
- [vLLM / PagedAttention](https://doi.org/10.1145/3600006.3613165)：缓解 KV cache 内存碎片，提高服务吞吐。
- [SGLang](https://arxiv.org/abs/2312.07104)：面向结构化 LLM 程序的运行时和共享前缀复用。
- [Prompt Cache](https://proceedings.mlsys.org/paper_files/paper/2024/hash/a66caa1703fe34705a4368c3014c1966-Abstract-Conference.html)：Prompt 模块复用与推理加速。
- [Sarathi-Serve](https://www.usenix.org/conference/osdi24/presentation/agrawal)：通过调度改善吞吐与延迟干扰。
- [DistServe](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin)：分离 Prefill 与 Decode 以分别调度资源。
- [RouteLLM](https://proceedings.iclr.cc/paper_files/paper/2025/hash/5503a7c69d48a2f86fc00b3dc09de686-Abstract-Conference.html)：在质量与成本约束下进行模型路由。

将这些论文与数据库问题连接起来：连续批处理类似算子调度；KV cache 类似有生命周期与预算的状态；Prefill/Decode 分离类似把特征不同的执行阶段放到不同资源池；模型路由则类似在多种物理算子实现之间做代价选择。

### 4.4 CPU+GPU 异构执行

GPU 决策不能只比较 Kernel 时间。端到端模型应为：

```text
T_gpu = T_queue + T_H2D + T_kernel + T_D2H + T_sync
T_cpu = T_cpu_kernel + T_memory_stall
```

只有在 `T_gpu` 明显更低且不违反内存预算和尾延迟目标时才应 Offload。关键设计点包括：

- 使用列式、连续、对齐的数据布局减少转换与拷贝。
- 使用 Pinned Memory、异步 Stream 和双缓冲重叠传输与计算。
- 对小输入保留 CPU Fallback，避免启动和传输开销。
- 让过滤、投影和解码尽量靠近数据源，减少传到 GPU 的字节。
- 在 GPU OOM、队列拥塞或设备故障时可降级。
- 把数据所有权、生命周期和 Stream 同步显式化，避免隐式全局同步。

[Mordred](https://www.vldb.org/pvldb/vol15/p2491-yogatama.pdf) 讨论 CPU/GPU 数据库中的异构执行与调度；[Apache Arrow 列式格式](https://arrow.apache.org/docs/format/Columnar.html) 是理解跨系统零拷贝数据接口的重要材料；[RAPIDS cuDF](https://docs.rapids.ai/api/cudf/stable/) 可用于了解 GPU DataFrame 的实际算子接口。

向量检索方面，[Faiss GPU](https://arxiv.org/abs/1702.08734) 展示了 GPU 相似度搜索的高吞吐路径；[DiskANN](https://papers.nips.cc/paper_files/paper/2019/hash/09853c7fb1d3f8ee67a61b6bf4a7f8e6-Abstract.html) 展示了受内存约束时基于 SSD 的大规模近似最近邻搜索。面试应理解 Recall、Latency、Memory 和更新成本之间的权衡，而不仅是记住 HNSW、IVF 或 PQ 名词。

### 4.5 Serverless Lakehouse 调度

Serverless 调度的困难是：到达率突发、任务很短、资源异构，而冷启动和排队可能占据主要延迟。需要联合考虑：

- Admission Control：避免过载导致所有请求尾延迟恶化。
- Warm Pool：维持少量预热 Worker，平衡闲置成本与冷启动。
- Resource Prediction：用 SQL 特征、历史运行和早期采样预测 CPU、内存、扫描量和 GPU 时间。
- Data Locality：存算分离时本地缓存仍然重要，调度不能只看空闲核数。
- Work Stealing / Morsels：短任务动态分配，缓解倾斜。
- Preemption：为交互式查询提供优先级，但要控制重算和状态迁移成本。
- Feedback Control：预测失败后基于队列、吞吐和背压在线扩缩。

相关文献：

- [Firecracker](https://www.usenix.org/conference/nsdi20/presentation/agache)：轻量 MicroVM 与隔离。
- [Starling](https://arxiv.org/abs/1911.11727)：基于云函数的分析查询执行。
- [Lambada](https://arxiv.org/abs/1912.00937)：Serverless 数据分析架构。
- [Caerus](https://www.usenix.org/conference/nsdi21/presentation/zhang-hong)：面向 Serverless 分析的资源管理。
- [Skyrise](https://arxiv.org/abs/2501.08479)：Serverless 数据处理系统与研究平台。

如果岗位提出“毫秒级完成调度”，你的回答要区分控制路径与数据路径：调度器不能在关键路径做复杂全局搜索，应预计算资源模板、维护近似索引、分层决策，并把精细调整交给执行期反馈。

### 4.6 企业数据分析智能体的可靠性

生产级 Agent 不应是“LLM 直接生成 SQL 然后展示答案”，而应是一个受约束、可验证的工作流：

```text
Intent -> schema/entity grounding -> plan -> SQL/tool calls
       -> syntax/type validation -> dry-run/cost guard
       -> execution -> result checks -> explanation with provenance
```

关键技术：

- **规划约束**：只允许从工具白名单和权限范围中选择动作。
- **语法约束**：[PICARD](https://aclanthology.org/2021.emnlp-main.779/) 展示增量约束解码，避免不合法 SQL。
- **执行反馈**：[ReAct](https://arxiv.org/abs/2210.03629) 把推理与行动交错，但企业系统还需要确定性的状态机和预算限制。
- **语义验证**：检查 Schema、Join Key、聚合粒度、时间范围和单位。
- **结果验证**：行数、空值、总量守恒、业务约束、对照查询和抽样证据。
- **安全性**：只读事务、查询超时、扫描预算、敏感列与行级权限。
- **可审计性**：记录模型、Prompt、工具调用、SQL、数据快照、结果和重试链路。

基准方面，[BIRD](https://papers.nips.cc/paper_files/paper/2023/hash/83fc8fab1710363050bbd1d4b8cc0021-Abstract-Datasets_and_Benchmarks.html) 强调真实数据库内容和知识推理；[Spider 2.0](https://proceedings.iclr.cc/paper_files/paper/2025/hash/46c10f6c8ea5aa6f267bcdabcb123f97-Abstract-Conference.html) 面向更复杂企业工作流；[InfiAgent-DABench](https://proceedings.mlr.press/v235/hu24s.html) 关注数据分析 Agent。评估时不要只看最终答案准确率，还要看 SQL 执行成功率、事实一致性、成本、延迟、重试率和人工接管率。

### 4.7 适合你切入的 AI-Native 研究题目

1. **AI Runtime Filter**：在 LLM 或 Embedding 前，用规则、小模型、向量索引或 Join Key 传播构建级联过滤器；研究误删风险、选择率估计和质量约束。
2. **Prompt 变化感知缓存**：把 Prompt、数据和模型依赖表示为版本化 DAG，按依赖范围做精确失效。
3. **SQL+LLM 自适应优化**：小样本执行估计 Token 分布、选择率和质量，再在线选择模型、Batch 与算子顺序。
4. **CPU/GPU 资源感知流水线**：将解码、过滤、Embedding、ANN 和 LLM 分阶段放置，联合优化传输和队列。
5. **可验证分析 Agent**：生成候选 SQL 后，用类型、约束、反例查询和差分执行验证计划。

---

## 5. 岗位二：Setats 流湖一体统一增量引擎文献综述

### 5.1 从公开架构理解课题

腾讯云公开的 [Setats 实时湖仓文档](https://intl.cloud.tencent.com/zh/document/product/1000/81251) 描述了一套统一流、批、状态的数据服务架构。公开信息中的关键点包括：

- 全量数据以列式格式存放在 COS/HDFS 等远程存储。
- 热数据在本地内存或磁盘以适合点查和更新的行式组织存在。
- 数据按 Partition 与 Bucket 组织，Manager/Worker 分工管理。
- 写入路径采用即时 Merge-on-Write 思路：查找历史记录，合并局部更新，生成完整行与 UpdateBefore/UpdateAfter Changelog，并异步持久化。
- 更新旧版本时可创建 Deletion Vector，读取时据此过滤被删除位置。
- 点查可使用 LSM Tree、Bloom Filter 与 Min/Max 等元数据索引。
- 远程数据路径强调全异步高性能 I/O，并面向 Flink、Spark、Doris、StarRocks 等多引擎开放。

公开文档中的未来能力与已落地能力需要在面试中谨慎区分。最稳妥的表达是：“基于公开架构，我理解其设计方向是……；具体生产实现与当前版本边界，需要结合团队内部信息确认。”

### 5.2 与主流 Lakehouse 的对照

| 系统/格式 | 核心抽象 | 更新方式关注点 | 面试时应掌握 |
|---|---|---|---|
| [Apache Paimon](https://paimon.apache.org/docs/master/concepts/) | 面向流式更新的 Lakehouse 表 | 主键表、LSM、MOR/COW/MOW、Deletion Vector | 与 Setats 最接近的公开参照之一 |
| [Apache Iceberg](https://iceberg.apache.org/spec/) | Snapshot、Manifest、Data/Delete File | Position/Equality Delete、Snapshot Isolation | 元数据裁剪与演进 |
| [Delta Lake](https://www.vldb.org/pvldb/vol13/p3411-armbrust.pdf) | Transaction Log + Parquet | 乐观并发、ACID、Compaction | 日志与对象存储一致性 |
| [Apache Hudi](https://hudi.apache.org/learn/tech-specs/) | Timeline、File Group、Index | Copy-on-Write / Merge-on-Read | 更新延迟与读放大权衡 |

[Lakehouse systems comparative study](https://www.vldb.org/cidrdb/papers/2023/p92-jain.pdf) 可帮助建立统一比较框架：元数据、并发控制、更新机制、文件布局、索引与多引擎一致性。

三个常见更新模式：

- **Copy-on-Write**：写时重写数据文件，读简单但写放大高。
- **Merge-on-Read**：写增量日志或 Delta，读时合并，写快但读放大和尾延迟高。
- **Merge-on-Write + Deletion Vector**：写入新版本并记录旧位置失效，避免立即重写大文件，但需要高效点查、DV 管理和后台整理。

没有全局最优模式。应根据更新比例、读取类型、对象大小、读取新鲜度和后台 Compaction 预算选择。

### 5.3 写入、合并与点查路径

一个可能的主键更新路径如下：

```text
incoming record
  -> partition/bucket routing
  -> primary-key lookup in local state / LSM
  -> fetch old row when partial update requires it
  -> merge into full row
  -> emit UpdateBefore + UpdateAfter changelog
  -> append new local buffer / sorted run
  -> mark old physical position in deletion vector
  -> asynchronous upload and metadata commit
```

一个远程点查路径可以分层设计：

```text
primary key
  -> partition and bucket pruning
  -> manifest / LSM level metadata
  -> Bloom and min-max pruning
  -> row-group / page location
  -> concurrent range GET
  -> decode key, deletion vector, and needed columns
  -> snapshot/version validation
  -> populate hot row cache
```

你应能分析其放大效应：

- 写放大：排序、Compaction、文件重写与多副本上传。
- 读放大：跨 LSM Level、增量文件、DV 和基础文件合并。
- 空间放大：旧版本、日志、DV、临时 Compaction 文件。
- 元数据放大：小文件、Manifest 与索引对象过多。

LSM 的系统性阅读可从 [LSM-based Storage Techniques Survey](https://arxiv.org/abs/1812.07527) 开始，再阅读 [RocksDB Compaction](https://github.com/facebook/rocksdb/wiki/Compaction) 的工程策略。[WiscKey](https://www.usenix.org/conference/fast16/technical-sessions/presentation/lu) 通过 Key/Value 分离降低 LSM 写放大，但会引入 Value Log GC 和额外读取，这正是典型的跨层权衡。

### 5.4 多级缓存与智能预取

在存算分离架构下，缓存至少可分为：

1. 元数据缓存：Snapshot、Manifest、文件统计、索引。
2. 索引缓存：Bloom、Fence Pointer、LSM Block Index。
3. 数据缓存：压缩 Page/Row Group、解压列向量、热行。
4. 状态缓存：增量计算与流处理状态。

缓存 Key 必须包含表、文件或对象 ID、版本/Snapshot、Offset/Length、编码和租户等足够信息，避免读到过期或越权数据。

策略上：

- LRU 对扫描污染敏感；频率与最近性应结合。
- [TinyLFU](https://arxiv.org/abs/1512.00727) 使用频率草图做准入控制。
- [SIEVE](https://www.usenix.org/conference/nsdi24/presentation/zhang-yazhuo) 提供简单且可扩展的淘汰思路。
- [CacheLib](https://www.usenix.org/system/files/osdi20-berg.pdf) 展示大规模缓存引擎的内存管理与工程设计。

预取不是越多越好。建议以以下信号控制：

- 顺序扫描检测、历史 Query Template、谓词范围和 Row Group 命中。
- 当前 Cache Pressure、I/O Queue Depth、带宽和对象存储请求限额。
- 过滤器尚未到达时避免盲目读取；可先获取元数据和 Key 列，待过滤后再取 Payload。
- 在流、增量、批模式切换时动态改变预取深度：流模式偏低延迟，批模式偏吞吐。

有效性指标应包含 Cache Hit Ratio、Byte Hit Ratio、污染率、Prefetch Accuracy、Coverage、Timeliness，以及节省的远程请求数和 P95/P99 延迟。

### 5.5 同时服务点查与批扫的存储格式

列式格式适合批量扫描和压缩，行式格式适合点查与更新。混合系统通常需要：

- 远程大文件按列组织，用 Row Group/Page 统计做裁剪。
- 本地热层或增量层按主键/行组织，快速合并 Update。
- 后台将增量数据排序、聚簇并合入列式基础文件。
- 用 Deletion Vector 或 Delete File 避免立即重写。

基础材料包括 [Dremel](https://www.vldb.org/pvldb/vol3/R29.pdf) 的嵌套列式表示、[Parquet Concepts](https://parquet.apache.org/docs/concepts/) 与 [ORC File Layout](https://hive.apache.org/docs/latest/language/languagemanual-orc/)。[BtrBlocks](https://zenodo.org/records/7936448) 展示现代块级压缩设计，[AnyBlob](https://www.vldb.org/pvldb/vol16/p2769-durner.pdf) 讨论从对象存储高效访问数据布局。

格式设计问题可用以下矩阵回答：

| 决策 | 点查影响 | 批扫影响 | 更新/维护影响 |
|---|---|---|---|
| Row Group 变小 | 少读无关数据 | 请求和元数据增多 | 小文件风险增加 |
| 按主键排序 | 点查和范围查更好 | 可能改善压缩 | 写入排序与 Compaction 更贵 |
| 更强压缩 | 远程字节更少 | 解码 CPU 更高 | 更新重写更贵 |
| Deletion Vector | 避免立即重写 | 读取需额外过滤 | DV 累积后需整理 |
| Key/Value 分离 | Key 探测轻 | Payload 可能随机读 | GC 和一致性更复杂 |

### 5.6 C++ 向量化算子与异步远程 I/O

高性能重写不等于把 Java 代码逐行翻译成 C++。需要重新审视数据布局、所有权、批处理和并发模型：

- 以列向量和 Selection Vector 传递过滤结果，避免逐行对象。
- 复用 Buffer，避免热路径频繁分配和引用计数争用。
- Kernel 内减少不可预测分支，必要时提供 SIMD 与标量 Fallback。
- 使用明确的 Sink/Source 或 Build/Probe 生命周期，防止依赖未完成。
- 对高基数、倾斜、NULL、字典编码和变长列保留正确慢路径。
- 使用 RAII 管理 Buffer、I/O Handle 与取消，避免异常路径泄漏。

远程 I/O 框架需要：

- Async Request + Completion，而不是每线程阻塞等待。
- 限制 In-flight 请求数和字节数，形成背压。
- 合并相邻 Range，避免大量小请求；但不能读取过多无效 Payload。
- 超时、重试、指数退避和幂等性。
- 查询取消能传到对象存储请求与解码任务。
- 把 I/O、解压、解码和算子计算流水化。

面试中可以提出两阶段读取：先异步读元数据、Key 列、DV 和过滤所需列，运行 Runtime Filter 后，再读取存活行的 Payload 列。这是你现有经验与 Setats 岗位最自然的结合点。

### 5.7 流、增量、批统一执行

“一套 SQL 零代码切换”不意味着三个模式使用完全相同的物理执行：

- **流模式**：无界输入、低延迟、Watermark、乱序与长期状态。
- **增量模式**：周期性消费变更，维护中间状态，只更新受影响结果。
- **批模式**：有界快照，强调吞吐、全局重排与大规模扫描。

统一的应是关系语义、Changelog 契约与优化框架；物理输入、状态表示、Checkpoint 和调度策略可以不同。

增量计算理论和系统脉络：

- [Naiad](https://www.microsoft.com/en-us/research/?p=165504)：带时间戳的数据流与迭代计算。
- [The Dataflow Model](https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf)：事件时间、Watermark、Trigger 与累积模式。
- [DBSP](https://www.vldb.org/pvldb/vol16/p1601-budiu.pdf)：用代数方式描述数据库增量计算。
- [Noria](https://www.usenix.org/conference/osdi18/presentation/gjengset)：部分状态化数据流和按需维护。
- [Flink Incremental Checkpointing](https://flink.apache.org/2018/01/30/managing-large-state-in-apache-flink-an-intro-to-incremental-checkpointing/)：基于 RocksDB 状态的增量 Checkpoint 工程路径。

Exactly-once 应被表述为端到端语义，而不是“Checkpoint 开关”：Source Offset 与算子状态必须在同一一致性切面恢复；Sink 需要事务、Two-Phase Commit 或幂等写；重放、乱序和失败恢复后，结果等价于每条记录生效一次。

### 5.8 适合你切入的 Setats 研究题目

1. **远程 Runtime Filter 下推**：联合选择 Bloom 大小、发布时间和消费层级，目标为最小化远程请求与解码工作。
2. **两阶段列读取**：Key/DV 优先读取，Payload 延迟读取；研究选择率和 RTT 对切换点的影响。
3. **模式感知缓存与预取**：在流、增量、批切换时动态调整缓存准入、对象粒度和预取深度。
4. **增量 Join 的两轮削减**：将 Yannakakis+ 扩展到带 Changelog 的状态维护，研究撤回与 Outer Join 语义。
5. **CPU/内存/I/O 自适应 Kernel**：在 Bitmap、Bloom、Hash Set 与无过滤间基于运行时信号切换。

---

## 6. 将你的经历转化为岗位证据

### 6.1 能力迁移矩阵

| 你的经历 | 可证明的能力 | 对 AI-Native 的表达 | 对 Setats 的表达 |
|---|---|---|---|
| Yannakakis+ | Join Graph、正确性、削减顺序 | 在昂贵 AI 算子前传播选择信息 | 流/批 Join 前减少远程读取与状态 |
| Runtime Filter | Build/Probe、Bloom/Bitmap、生命周期 | 级联小模型/Embedding/LLM | Bloom/MinMax/分区过滤下推 |
| CPU 优化 | Kernel、向量化、缓存局部性 | Prompt 预处理和 CPU Fallback | C++ 向量化与解码 |
| 内存优化 | 预算、峰值、退化路径 | KV cache 与 GPU Memory 管理 | LSM Block、状态、过滤器预算 |
| I/O 优化 | 扫描裁剪、并发、测量 | 多模态数据路径、向量索引 | COS/HDFS Range GET 与预取 |
| 查询优化 | 代价模型、基数、重排 | 延迟/费用/质量联合优化 | 读写放大与模式选择 |

### 6.2 一个可信的项目讲述模板

使用“问题 - 约束 - 设计 - 验证 - 反例”结构：

> 问题：多表 Join 在某类图或星型查询上产生大量无效扫描和中间结果。约束：过滤器有内存预算，Build/Probe 有依赖，Outer Join 方向和 NULL 语义不能破坏。设计：在优化器识别 Join 结构，规划两轮半连接削减；执行器提供 Bloom/Bitmap/Hash Fallback，并根据 NDV、值域和预算选择。验证：在 `[真实工作负载]` 上比较裸查询结果与基线，记录端到端时间、扫描行数、CPU、峰值内存和过滤器到达时间。反例：高选择率、过滤器迟到或基数误估时可能变慢，因此增加成本门控和运行时降级。

这个回答比只说“实现了 Yannakakis 算法”更强，因为它同时展示理论、优化器、执行器、正确性与实验能力。

### 6.3 你需要主动补齐的知识

第二岗优先：

- C++17/20：Move、RAII、Allocator、并发原语、Coroutine、Memory Model。
- LSM Compaction、Bloom/Index Block、WAL、Snapshot 与 MVCC。
- Parquet/ORC 编码、Page/Row Group、Predicate Pushdown。
- Flink Changelog、Watermark、Checkpoint、State Backend、Two-Phase Commit。
- 对象存储语义、Range GET、重试、限流与小文件问题。

第一岗优先：

- Transformer Prefill/Decode、KV cache、Continuous Batching。
- GPU Memory Hierarchy、Stream、Pinned Memory、Kernel Launch。
- Embedding、ANN、Recall/Latency/Memory 权衡。
- Text-to-SQL、Agent 工具调用、约束解码与执行验证。
- 多目标/质量约束优化与模型路由。

### 6.4 四周准备计划

**第 1 周：巩固共同基础**

- 复述 Yannakakis、Predicate Transfer、Bloom 公式与 Outer Join 安全方向。
- 阅读 X100、Morsel、Velox；对自己的 Runtime Filter 做一次 CPU/内存/I/O 分解。
- 准备 3 分钟项目介绍和 10 分钟深挖版本。

**第 2 周：集中突破 Setats**

- 阅读 Setats 公开架构、Paimon 主键表、Iceberg Spec、LSM Survey。
- 手画写入、点查、Compaction、Checkpoint 和失败恢复路径。
- 用 C++ 写一个批量 Bloom Probe 或异步读取小原型，并能解释性能计数器。

**第 3 周：集中突破 AI-Native**

- 阅读 LOTUS、Palimpzest、Orca、vLLM、SGLang、DistServe。
- 为 `SQL -> SemanticFilter -> Join -> Aggregate` 设计两个候选计划和代价模型。
- 设计安全缓存 Key、失效规则与小模型到大模型的级联路由。

**第 4 周：面试化与查漏补缺**

- 每天完成一轮 45 分钟模拟面试：项目、基础、系统设计、行为题。
- 对每个设计给出正确性、资源预算、降级路径、指标和故障注入。
- 准备真实数字、失败实验和你改变设计判断的案例。

---

## 7. 可能的面试问题与参考答案

以下答案是表达框架，不建议逐字背诵。涉及项目结果时必须替换成真实数据。

### 7.1 个人背景与岗位动机

#### Q1：你的研究为什么适合这两个岗位？

**参考答案：** 我的核心能力是把关系语义、优化器决策和底层资源代价连接起来。Yannakakis+ 让我熟悉如何通过半连接传播减少无效中间结果；Runtime Filter 项目让我实际处理 Build/Probe 依赖、Bloom/Bitmap 预算、Outer Join 正确性，以及 CPU、内存和 I/O 不同瓶颈下的取舍。Setats 中这些能力可直接用于远程扫描裁剪、向量化和增量 Join；AI-Native 中我会把 LLM、Embedding 和 GPU 推理视作更昂贵、带质量维度的算子，研究其下推、缓存、批处理和路由。

#### Q2：两个岗位中你更匹配哪一个？

**参考答案：** 从现有经验看，流湖一体岗位与我的查询执行和 Runtime Filter 更直接匹配，尤其是 C++ 向量化、远程 I/O 裁剪和 Join 状态优化。但我也非常看好 AI-Native 方向，因为我的差异化是能从数据系统角度优化 AI 算子，而不是只做模型调用。如果团队更需要短期落地，我能在 Setats 快速贡献；如果需要探索新代价模型和 SQL+LLM 优化，我也有清晰的迁移路径。

#### Q3：讲一个优化失败或变慢的案例。

**参考答案：** 选择一个真实案例，例如过滤器在高选择率或迟到场景下变慢。说明最初假设、通过 Profile 发现 Build/广播/等待超过裁剪收益、如何加入选择率或时间门控、如何保留无过滤 Fallback，以及最终在哪些区间启用。面试官更关注你是否能推翻自己的假设，而不是所有实验都成功。

### 7.2 查询算法与运行时过滤

#### Q4：解释 Yannakakis 算法及其适用条件。

**参考答案：** 对无环 Join Query，先构造满足运行交集性质的 Join Tree。自底向上对父子关系做半连接，删除父侧或指定方向上没有匹配的元组；再自顶向下做反向削减，使关系达到全约简；最后按 Join Tree 执行。其优势是避免产生无法进入结果的巨大中间结果。适用前提是无环结构和相应 Join 语义；对环查询需做分解、使用广义算法或接受近似过滤。

#### Q5：Runtime Filter 和半连接有什么区别？

**参考答案：** 半连接是关系代数算子，输出一侧中存在匹配的完整元组，通常是精确语义；Runtime Filter 是执行期的摘要和优化机制，可能只包含 Key 的 Bloom、范围或值集，并下推给 Scan。Bloom 有假阳性，因此可能保留无匹配行，但不能有假阴性。两者目标相似，但 Runtime Filter 更强调异步发布、预算、传输和底层 Scan 能否消费。

#### Q6：如何选择 Bloom Filter 参数？

**参考答案：** 根据 Build Side NDV `n` 和位预算 `m`，最优哈希数约为 `(m/n)ln2`，假阳性率约为 `(1-exp(-kn/m))^k`。工程上还要限制哈希 CPU、对齐内存、并发构建方式和网络大小。如果 NDV 估计超预算，我会提高可接受假阳性率、切换到分区/MinMax 过滤，或完全禁用；运行期对实际过滤率做反馈。

#### Q7：什么情况下 Runtime Filter 会变慢？

**参考答案：** 高选择率、Build Side NDV 很大、过滤器传播昂贵、消费者扫描很快、过滤器到达晚、哈希计算比下游工作更贵，或过滤器导致缓存和内存带宽压力时。应比较端到端避免工作与构建、探测、同步成本，并提供 Late Filter、超预算和低收益时的降级路径。

#### Q8：过滤器异步到达时如何设计？

**参考答案：** Scan 不一定要阻塞等待。可设小的等待预算；先读取元数据或缓存数据；过滤器到达后只对剩余 Split 生效。调度器记录每个 Split 是否已发出，避免重复或漏扫。若过滤器发布前 Build 未完成，不能把不完整摘要当作最终过滤器，否则会产生假阴性。可以用版本和原子发布状态保证只消费 Finalized Filter。

#### Q9：Outer Join 中哪些 Runtime Filter 下推是安全的？

**参考答案：** 对 `L LEFT JOIN R`，L 是保留侧，可用 L Key 过滤 R，因为 R 中不匹配 L 的行不会输出；不能反过来用 R 删除 L，否则丢失 NULL 扩展行。RIGHT 相反，FULL 通常都不安全。还需检查谓词、NULL-Safe Equality 和 Join 重排后的方向。

#### Q10：如何证明一个 Runtime Filter 优化正确？

**参考答案：** 先从关系语义证明过滤方向不会删除可能进入最终结果的元组；Bloom 保证无假阴性；Build 完成和发布形成明确依赖。测试上比较优化开关前后的裸查询结果，覆盖 INNER/LEFT/RIGHT/FULL、NULL、重复值、空表、倾斜、并发和 Spill，并启用执行器验证与故障注入。

#### Q11：基数估计不准时怎样做鲁棒优化？

**参考答案：** 静态阶段使用不确定性区间和保守门控，避免把计划押在单点估计上；执行期观察 Build NDV、选择率、实际行数和资源压力，动态改变过滤器类型、Join 算法或并行度。计划要有低成本 Fallback，避免切换本身比收益更贵。

### 7.3 执行引擎与性能分析

#### Q12：怎样判断系统是 CPU、内存还是 I/O 受限？

**参考答案：** 先做 Wall Time 和算子级分解。CPU 受限常见特征是核心利用率高、IPC/分支/指令数决定吞吐；内存受限可见 LLC Miss、内存带宽接近上限、核数增加但吞吐不增；I/O 受限则线程等待、远程字节、请求 RTT 和 Queue Depth 主导。要用控制变量改变核数、缓存命中和数据规模验证，不能只凭一次 Profile 判断。

#### Q13：为什么向量化执行比逐元组快？

**参考答案：** 它摊薄函数调用和解释分派，改善数据局部性，使编译器更容易自动向量化，并可用 Selection Vector 避免物化。但批太大会增加缓存压力、内存峰值和尾延迟，因此需要结合列宽、算子和并发度调参。

#### Q14：Morsel-Driven Parallelism 解决什么问题？

**参考答案：** 把输入拆成小而可调度的 Morsel，工作线程动态领取，以较低调度成本实现负载均衡、处理倾斜，并结合 NUMA Locality。对短任务或远程 I/O 系统，还应把 Morsel 大小与请求合并、取消响应和缓存局部性共同考虑。

#### Q15：你会如何优化一个 C++ Hash/Bloom Probe Kernel？

**参考答案：** 先测而不是猜。确认数据布局、哈希成本、分支预测、Cache Miss 和内存带宽；批量读取 Key，预取或并行计算哈希，减少虚调用和边界检查，输出 Selection Vector；对稠密整数值域可选 Bitmap；保留标量 Fallback 和 NULL/变长类型慢路径。最后报告端到端收益，避免 Kernel 微基准掩盖 I/O 或同步瓶颈。

### 7.4 AI-Native Data Infra

#### Q16：如何把 LLM 调用纳入 SQL 优化器？

**参考答案：** 将其建模为具有输入 Schema、输出 Schema、选择率、非确定性、质量和外部成本的逻辑算子。物理实现可有不同模型、Prompt、Batch、缓存和路由。优化器优先把便宜确定性谓词下推，在质量约束下比较模型选择、算子顺序和并行策略；执行期用样本校准 Token、选择率和延迟。

#### Q17：AI 算子的代价模型应包含什么？

**参考答案：** 除行数外还要有 Token 长度分布、Batch 曲线、模型和 GPU、队列、Prefill/Decode、KV cache、CPU-GPU 传输、缓存命中、速率限制和重试。目标通常是延迟、费用、GPU 时间和质量损失的加权或约束优化，至少报告 P95/P99，不只看平均值。

#### Q18：Prompt 变化后哪些缓存仍可复用？

**参考答案：** 精确结果缓存只有在规范化 Prompt、输入快照、模型版本、采样、RAG/工具和权限等语义依赖一致时才安全。KV cache 通常只能复用最长相同前缀；中间位置变化会使其后的因果状态失效。Embedding 或算子结果可按数据行和模型版本增量失效。还要处理多租户隔离和 Lineage。

#### Q19：什么时候应该把算子放到 GPU？

**参考答案：** 比较端到端 `排队 + H2D + Kernel + D2H + 同步` 与 CPU 路径，而不是只比 Kernel。大批量、高算术强度、可合并访存的算子更适合 GPU；小输入、强分支或频繁往返可能在 CPU 更快。系统要支持异步流水、内存预算、拥塞感知和 CPU Fallback。

#### Q20：如何降低 LLM 查询的延迟和成本？

**参考答案：** 先用 SQL 谓词和索引裁剪；再做结果缓存、Prefix/KV 复用和连续批处理；用小模型或规则级联路由，将难例发送给大模型；分离 Prefill/Decode 资源；限制输出长度与重试；最后在质量约束下优化，而不是以降低成本为由静默降低正确率。

#### Q21：如何实现毫秒级 Serverless 调度？

**参考答案：** 关键路径使用分层和近似决策：先按预计算资源模板、SLO 和数据位置选择池，再进行 O(1) 或近似队列分配；Warm Pool 缓解冷启动；运行期用 Morsel、Work Stealing 和反馈控制修正预测。复杂全局优化放在离线或慢路径，并通过 Admission Control 防止过载。

#### Q22：如何让数据分析 Agent 可用于生产？

**参考答案：** 把 Agent 放进受控状态机：Schema Grounding、计划、SQL/工具白名单、语法与类型检查、只读 Dry Run、成本预算、执行和结果校验。对关键结论提供 SQL、数据快照和证据；使用对照查询或业务约束验证；记录完整 Trace，并设置超时、重试和人工接管。评估要覆盖事实一致性、执行成功、成本和尾延迟。

### 7.5 流湖一体与存储引擎

#### Q23：Setats 类系统为什么需要本地行存和远程列存？

**参考答案：** 远程列存适合高压缩和批量扫描，但点查和小更新会读放大；本地行式热层适合主键查找、合并局部更新和低延迟状态访问。后台将热层整理为远程列式文件。代价是两种布局、一致性、缓存失效和 Compaction 更复杂，需要明确 Snapshot 与 Changelog 契约。

#### Q24：Merge-on-Read、Copy-on-Write 和 Merge-on-Write 如何选择？

**参考答案：** COW 读简单但写放大高；MOR 写快但查询要合并增量，读放大和尾延迟高；带 DV 的 MOW 可写入新版本并标记旧位置，减少立即重写，但点查、DV 和后台整理更复杂。选择取决于更新率、读取新鲜度、点查/批扫比例、对象存储成本与 Compaction 预算。

#### Q25：LSM Tree 的主要性能权衡是什么？

**参考答案：** 顺序写入带来高写吞吐，但查询需跨多个 Level/Run，Compaction 产生写放大和尾延迟。Bloom、Block Index 和缓存降低读放大；Leveled 与 Tiered Compaction 在空间、读和写放大间取舍；还需处理 Tombstone、Snapshot 和大 Value。不能只说写快，要量化三种放大。

#### Q26：如何设计远程点查？

**参考答案：** 先按 Partition/Bucket 和 Snapshot 定位，再用 Manifest、LSM 元数据、Bloom/MinMax 排除文件，定位 Row Group/Page，合并相邻 Range GET 并异步并发。优先读 Key、DV 和必要列，验证版本后再取 Payload；建立多级缓存和请求限流，并记录远程字节、请求数和 P99。

#### Q27：如何设计智能预取而不污染缓存？

**参考答案：** 预取由顺序访问、查询模板、谓词和消费速度触发，并受到 Cache Pressure、I/O Queue 与请求额度限制。使用准入策略区分一次性扫描和高复用对象；过滤器未到达时只预取元数据或 Key；运行期根据 Accuracy、Coverage 和 Timeliness 调整深度，取消已无用请求。

#### Q28：流、增量、批怎样共享一套 SQL？

**参考答案：** 共享关系语义、逻辑计划和 Changelog 契约，针对模式选择不同物理实现。流使用无界 Source、Watermark 和长期状态；增量按变更批次维护受影响状态；批读取一致快照并可做全局优化。模式切换必须定义状态引导、快照边界、UpdateBefore/After 和故障恢复。

#### Q29：Exactly-once 如何端到端实现？

**参考答案：** Checkpoint 在一致性切面记录 Source Offset 和算子状态；恢复时从对应 Offset 重放。Sink 必须支持事务/Two-Phase Commit 或基于唯一 Key 和 Epoch 幂等写入。还要考虑 Checkpoint 完成但外部提交状态不明、重试、乱序和状态 TTL。最终要求是失败恢复后的外部可见结果等价于每条记录只生效一次。

#### Q30：Deletion Vector 何时会成为问题？

**参考答案：** DV 很大或高度碎片化时，扫描需要读取和探测更多元数据，存活行不连续也会破坏向量化与 Range 合并。应监控 DV 密度、文件年龄和查询热度，达到阈值后重写数据文件并合并 DV；Compaction 要限速并与前台 I/O 隔离。

### 7.6 系统设计题

#### Q31：设计一个跨多表 Join 的分布式 Runtime Filter 系统。

**参考答案骨架：**

1. 优化器从 Join Graph 选择过滤传播方向，检查 Outer Join/NULL 语义。
2. 根据 NDV、值域、消费者数量、远程字节和预算选择 In-list、Bitmap、Bloom、MinMax 或分区过滤。
3. Build Operator 输出局部摘要；Coordinator 分层合并并以版本化 Final 状态发布。
4. Scan 等待有限时间，已调度 Split 不回滚，剩余 Split 下推过滤；必要时二阶段读 Key/Payload。
5. 设置每过滤器内存预算、网络压缩、超时和无过滤 Fallback。
6. 指标包括构建/发布时间、到达比例、过滤率、假阳性、节省字节、Probe CPU、P95/P99。
7. 测试包括高低选择率、倾斜、迟到、节点失败、空 Build、Outer Join 和基数误估。

#### Q32：设计一个 SQL+LLM 的语义过滤执行器。

**参考答案骨架：**

1. 逻辑算子声明输入、Prompt、模型候选、质量要求和输出 Schema。
2. 优化器先做传统谓词/Join 裁剪，再比较规则、小模型、Embedding、LLM 的级联计划。
3. 执行器规范化输入并查精确结果缓存；按共享前缀和长度分桶批处理。
4. 调度器基于 GPU 队列、KV cache、SLO 和费用路由模型，支持 Prefill/Decode 分离。
5. 输出附带模型/Prompt/数据版本、置信度和证据；关键任务做抽样复核或双模型验证。
6. Prompt/数据/模型变更按依赖 DAG 失效缓存，多租户严格隔离。
7. 评价延迟、Token/费用、GPU 利用率、缓存命中、质量、失败率和尾延迟。

#### Q33：设计一个兼顾秒级更新、点查和批扫的流湖存储引擎。

**参考答案骨架：**

1. 远程对象存储保存列式 Base File，本地热层按 Partition/Bucket 与主键组织。
2. 写入经 WAL/版本化 Buffer，点查旧值，合并 Update，输出 Changelog，记录旧位置 DV。
3. 元数据提交形成原子 Snapshot；失败恢复重放 WAL，并确保对象上传与元数据提交幂等。
4. 点查走 LSM/Bloom/Index 与热行缓存；批扫走分区、文件、Row Group 和 Runtime Filter 裁剪。
5. 后台 Compaction 合并增量、清理 DV 和小文件，采用配额与前台隔离。
6. 多级缓存区分元数据、索引、压缩块和解压向量；预取按模式自适应。
7. 测试新鲜度、吞吐、P99、读写/空间放大、故障恢复、热点倾斜和模式切换。

---

## 8. 阅读清单与优先级

### 8.1 P0：面试前必须掌握

| 主题 | 材料 | 读完必须能回答 |
|---|---|---|
| 半连接削减 | [Yannakakis 1981](https://www.sigmod.org/publications/dblp/db/conf/vldb/Yannakakis81.html) | 两轮算法、无环性、全约简、工程成本 |
| 现代过滤传播 | [Predicate Transfer](https://www.vldb.org/cidrdb/papers/2024/p22-yang.pdf) | 与 Join Order、Bloom 和鲁棒性的关系 |
| 向量化 | [MonetDB/X100](https://www.cidrdb.org/cidr2005/papers/P19.pdf) | 为什么批处理更快，批大小取舍 |
| 并行执行 | [Morsel-Driven Parallelism](https://www-db.in.tum.de/~leis/papers/morsels.pdf) | 倾斜、NUMA、动态调度 |
| Setats | [腾讯云公开架构](https://intl.cloud.tencent.com/zh/document/product/1000/81251) | 行/列热冷层、MOW、DV、异步 I/O |
| Lakehouse | [Paimon Concepts](https://paimon.apache.org/docs/master/concepts/) 与 [Table Modes](https://paimon.apache.org/docs/master/primary-key-table/table-mode/) | LSM、MOR/COW/MOW、主键更新 |
| LSM | [LSM Survey](https://arxiv.org/abs/1812.07527) | 读写空间放大、Compaction |
| 流语义 | [Dataflow Model](https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf) | Watermark、Trigger、事件时间 |
| 语义算子 | [LOTUS](https://arxiv.org/abs/2407.11418) | 如何把 LLM 作为声明式算子优化 |
| AI 数据管道 | [Palimpzest](https://arxiv.org/abs/2405.14696) | 成本、质量与计划搜索 |
| LLM 服务 | [Orca](https://www.usenix.org/conference/osdi22/presentation/yu) 与 [vLLM](https://doi.org/10.1145/3600006.3613165) | 连续批处理、KV cache、PagedAttention |
| Agent 验证 | [PICARD](https://aclanthology.org/2021.emnlp-main.779/) 与 [Spider 2.0](https://proceedings.iclr.cc/paper_files/paper/2025/hash/46c10f6c8ea5aa6f267bcdabcb123f97-Abstract-Conference.html) | 约束生成和企业级任务难点 |

### 8.2 P1：用于系统设计深挖

- [Velox](https://vldb.org/pvldb/vol15/p3372-pedreira.pdf)
- [Apache Iceberg Specification](https://iceberg.apache.org/spec/)
- [Delta Lake](https://www.vldb.org/pvldb/vol13/p3411-armbrust.pdf)
- [Apache Hudi Technical Specification](https://hudi.apache.org/learn/tech-specs/)
- [DBSP](https://www.vldb.org/pvldb/vol16/p1601-budiu.pdf)
- [Noria](https://www.usenix.org/conference/osdi18/presentation/gjengset)
- [CacheLib](https://www.usenix.org/system/files/osdi20-berg.pdf)
- [SIEVE](https://www.usenix.org/conference/nsdi24/presentation/zhang-yazhuo)
- [SGLang](https://arxiv.org/abs/2312.07104)
- [Sarathi-Serve](https://www.usenix.org/conference/osdi24/presentation/agrawal)
- [DistServe](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin)
- [Mordred](https://www.vldb.org/pvldb/vol15/p2491-yogatama.pdf)
- [Firecracker](https://www.usenix.org/conference/nsdi20/presentation/agache)
- [Caerus](https://www.usenix.org/conference/nsdi21/presentation/zhang-hong)

### 8.3 P2：用于研究选题与追问

- [Free Join](https://arxiv.org/abs/2301.10841)
- [Robust Predicate Transfer](https://arxiv.org/abs/2502.15181)
- [Including Bloom Filters in Bottom-up Optimization](https://arxiv.org/abs/2505.02994)
- [WiscKey](https://www.usenix.org/conference/fast16/technical-sessions/presentation/lu)
- [BtrBlocks](https://zenodo.org/records/7936448)
- [AnyBlob](https://www.vldb.org/pvldb/vol16/p2769-durner.pdf)
- [Naiad](https://www.microsoft.com/en-us/research/?p=165504)
- [Prompt Cache](https://proceedings.mlsys.org/paper_files/paper/2024/hash/a66caa1703fe34705a4368c3014c1966-Abstract-Conference.html)
- [RouteLLM](https://proceedings.iclr.cc/paper_files/paper/2025/hash/5503a7c69d48a2f86fc00b3dc09de686-Abstract-Conference.html)
- [Faiss GPU](https://arxiv.org/abs/1702.08734)
- [DiskANN](https://papers.nips.cc/paper_files/paper/2019/hash/09853c7fb1d3f8ee67a61b6bf4a7f8e6-Abstract.html)
- [BIRD](https://papers.nips.cc/paper_files/paper/2023/hash/83fc8fab1710363050bbd1d4b8cc0021-Abstract-Datasets_and_Benchmarks.html)
- [InfiAgent-DABench](https://proceedings.mlr.press/v235/hu24s.html)

---

## 9. 面试前最后检查表

### 项目证据

- [ ] 能在 3 分钟内讲清问题、设计、正确性、实验和失败场景。
- [ ] 所有数字真实，可解释机器、数据集、基线和重复次数。
- [ ] 能画出优化器到执行器的调用与依赖路径。
- [ ] 能解释为何没有选择另一种过滤器或 Join 算法。

### 系统基础

- [ ] 能推导 Bloom 公式并说明预算与退化策略。
- [ ] 能解释 Outer Join、NULL 和过滤方向。
- [ ] 能区分 CPU、内存带宽、I/O、网络和同步瓶颈。
- [ ] 能解释向量化、Selection Vector、Morsel 与背压。

### Setats

- [ ] 能手画写入、点查、批扫、Compaction 和恢复路径。
- [ ] 能比较 COW、MOR、MOW 与 Deletion Vector。
- [ ] 能解释 LSM 三种放大和缓存/预取指标。
- [ ] 能解释流、增量、批的统一边界与 Exactly-once。

### AI-Native

- [ ] 能写出延迟/费用/GPU/质量联合代价模型。
- [ ] 能区分结果缓存、Prefix/KV cache 和中间结果缓存。
- [ ] 能计算 GPU Offload 的端到端成本。
- [ ] 能设计受约束、可验证、可审计的数据分析 Agent。

---

## 10. 最终定位句

> 我的优势是把查询理论转化为资源感知的系统优化：用半连接削减与运行时过滤减少无效数据，用向量化和异构执行降低每条有效数据的成本，再用正确性约束、代价模型和运行时反馈决定何时启用、何时降级。这条方法论既适用于 Setats 的远程存储与增量计算，也适用于 AI-Native 平台中的 LLM、Embedding 和 GPU 算子。

