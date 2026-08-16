# ByteDance 2027 Research Scientist Preparation Guide

## Data Management, Large Language Models, AI Agents, and Full-Stack AI Infrastructure

- Target role: Research Scientist - Technologies of Data Management, LLM and AI Agents
- Program: Global Tech Research Program - 2027 Start (PhD)
- Candidate anchor: query evaluation and optimization, Yannakakis+, runtime filters, and CPU/memory/I/O bottleneck analysis
- Scope: literature review, capability mapping, research ideas, study plan, and interview questions with model answers
- Updated: 2026-08-10

> The most credible positioning is not to claim equal depth across every topic in this unusually broad job description. Use query optimization and runtime filtering as the research anchor, demonstrate strong depth in multimodal data management and vector retrieval, and show systems fluency across observability, storage, heterogeneous scheduling, and safe infrastructure agents.

---

## 0. How to Use This Guide

Read this document in three passes:

1. Read Sections 1, 2, and 10 to form a clear role-fit narrative.
2. Study Sections 3 through 9 until you can explain each design tradeoff without notes.
3. Rehearse Sections 12 and 13 aloud under time limits, then use Section 14 to close knowledge gaps.

For almost every systems question, answer in the same order:

1. Define semantics, SLOs, and correctness or quality constraints.
2. Describe the logical plan and physical data path.
3. Build a cost model across CPU, memory, I/O, network, GPU, energy, and money.
4. Explain adaptive behavior, failure handling, and fallback.
5. Name the measurements, baselines, ablations, and adversarial cases.

Never invent project numbers. Replace placeholders with measurements from your actual work:

- Data scale: [rows, bytes, queries, or graph size]
- Baseline: [native optimizer, no filter, or alternative filter]
- Result: [latency, bytes read, CPU cycles, peak memory]
- Failure case: [high selectivity, late filter, skew, bad estimate, or budget exhaustion]

---

## 1. Executive Summary

### 1.1 What This Role Actually Combines

The job description covers both directions of AI-systems research:

- **Infrastructure for AI:** multimodal query engines, vector retrieval, elastic file systems, DPU acceleration, GPU/CPU/MEM scheduling, checkpointing, and AI-cluster observability.
- **AI for infrastructure:** Text-to-SQL, automated tuning, fault diagnosis, Auto Skills, and self-evolving operational agents.

The breadth suggests that a strong candidate should present one deep research identity plus credible adjacent systems knowledge. Your strongest direct match is:

1. multimodal data management and semantic query optimization;
2. hybrid SQL/vector filtering and candidate reduction;
3. AI for query optimization and runtime adaptation;
4. storage and execution-path optimization through CPU/memory/I/O analysis.

The largest gaps to close are:

- GPU-cluster communication and observability;
- cloud-native distributed vector indexing;
- AI-training storage and checkpointing;
- DPU/SmartNIC data paths;
- heterogeneous resource and power scheduling;
- safe lifecycle management for self-evolving agents.

### 1.2 Recommended Positioning

> My research focuses on avoiding expensive downstream work by exploiting query structure, runtime information, and resource behavior. Yannakakis-style reductions and runtime filters let a system remove tuples before scans, joins, and materialization become expensive. In AI-native data systems, I would extend the same principle to exact predicate pushdown, filtered vector search, semantic candidate generation, factorized inference, model cascades, and resource-aware placement, while making recall and semantic quality explicit constraints.

This sentence creates a coherent bridge across the entire JD:

| Existing experience | Transferable principle | New role application |
|---|---|---|
| Yannakakis+ | Propagate existence information before materialization | Reduce multiway semantic joins before LLM/VLM verification |
| Runtime filters | Build a compact summary and consume it near the source | Filtered ANN, metadata pruning, semantic cascades |
| CPU-bound optimization | Reduce instructions, branches, and dispatch | Vector distance kernels, parsing, decoding, small-model proxies |
| Memory-bound optimization | Budget state and improve locality | HNSW/PQ, KV cache, checkpoint staging, TSDB indexes |
| I/O-bound optimization | Skip bytes and overlap useful work with latency | SSD vector search, remote datasets, checkpoint loading |
| Query cost models | Compare plans under uncertain cardinality | Joint latency, money, energy, recall, and quality optimization |

### 1.3 A 60-Second Introduction

> My research is at the boundary between query optimization and execution. I have worked on Yannakakis-style semijoin reductions, join planning, and runtime filters, including when filters help or hurt under CPU, memory, and I/O bottlenecks. I am interested in this role because AI-native infrastructure makes the same optimization problem more challenging: SQL, full-text search, vector retrieval, and LLM operators have different cost and correctness models, while execution spans storage, networks, CPUs, and heterogeneous accelerators. My immediate contribution would be cost- and quality-aware multimodal query optimization, especially candidate reduction before expensive semantic operators. I also want to extend this work toward distributed vector indexes and safe AI-for-infrastructure control loops.

### 1.4 Important Application Details

The posting explicitly requires a 2027 onboarding date. Put the following near the top of the resume:

- Expected PhD graduation: [month and year]
- Earliest onboarding date: [date]
- Work location or mobility: [location]

The role also values independent design documents, demos, and first-author publications. Prepare:

- one two-page research statement;
- one architecture document for a system you personally designed;
- one reproducible demo with an end-to-end benchmark;
- a clear contribution statement for every paper or project;
- a failure story showing how evidence changed your design.

---

## 2. A Unified Technical Map

~~~text
Natural-language or programmatic intent
              |
              v
Schema, catalog, data, policy, and topology grounding
              |
              v
Unified logical algebra
  SQL | full-text | vector | semantic operators | agent tools
              |
              v
Cost, quality, and risk-aware optimization
  cardinality | recall | quality | latency | money | energy | uncertainty
              |
              v
Physical execution and placement
  CPU | GPU | HBM | DRAM | DPU | network | local SSD | remote storage
              |
              v
Scheduling, elasticity, and state movement
  model weights | checkpoints | KV cache | vector index | workflow state
              |
              v
Observability and verification
  metrics | traces | logs | profiles | provenance | result checks
              |
              v
Guarded AI-for-infrastructure loop
  diagnose -> propose -> validate -> canary -> act -> verify -> rollback
~~~

The essential interview skill is cross-layer reasoning. Examples:

- A vector filter reduces candidates, but does it preserve recall under filter-vector correlation?
- A DPU saves host CPU, but do PCIe crossings and weak onboard cores erase the gain?
- More GPUs improve throughput, but do CPU preprocessing, host memory, or network collectives become the bottleneck?
- A self-evolving agent learns a useful skill, but can the system prove its provenance, permissions, and rollback behavior?
- A TSDB tuner improves compression, but does added compaction delay the telemetry needed to control the tuner itself?

---

## 3. Your Core Foundation as the Unifying Research Story

### 3.1 Yannakakis, Predicate Transfer, and Runtime Pruning

[Yannakakis 1981](https://www.sigmod.org/publications/dblp/db/conf/vldb/Yannakakis81.html) evaluates acyclic joins through a bottom-up semijoin reduction, a top-down reduction, and final joins over reduced relations. Its continuing systems lesson is:

> Propagate compact evidence of possible contribution before producing expensive intermediate results.

Modern work generalizes this idea. [Predicate Transfer](https://www.vldb.org/cidrdb/papers/2024/p22-yang.pdf) propagates filters across a join graph. [Free Join](https://arxiv.org/abs/2301.10841) broadens the execution space between binary and worst-case optimal joins. A particularly relevant 2026 perspective is [I Cannot Believe It Is Not Yannakakis](https://www.vldb.org/cidrdb/2026/i-cant-believe-its-not-yannakakis-pragmatic-bitmap-filters-in-microsoft-sql-server.html), which studies pragmatic bitmap filtering within a mature industrial optimizer.

Runtime pruning mechanisms include:

| Mechanism | Strength | Weakness | AI-native analogue |
|---|---|---|---|
| Min/max or zone map | Tiny and cheap | Weak on sparse or multimodal keys | Partition or segment pruning |
| Exact set | No false positives | High memory at large NDV | Exact metadata candidate set |
| Bloom filter | Bounded memory, no false negatives | Probe CPU and false positives | Safe approximate relational prefilter |
| Bitmap | Very fast probe on dense domains | Domain-sensitive memory | Filtered ANN eligibility bitmap |
| Learned proxy | Can model semantic relevance | May create false negatives | Small-model or embedding cascade |

For a Bloom filter:

~~~text
false_positive_rate ~= (1 - exp(-k * n / m))^k
optimal_hash_count  = (m / n) * ln(2)
bits_per_item       = -ln(p) / (ln(2)^2)
~~~

The engineering decision is broader than the formula:

~~~text
ExpectedBenefit =
    avoided_bytes * io_cost_per_byte
  + avoided_rows * downstream_cpu_cost
  + avoided_network * network_cost_per_byte
  + avoided_ai_calls * expected_ai_call_cost

ExpectedCost =
    build_cpu + build_memory + publish_cost
  + probe_cpu + waiting + uncertainty_margin
~~~

Enable a filter only when expected benefit exceeds expected cost and the semantic safety conditions hold.

### 3.2 What Changes for AI Operators

A relational Bloom filter may retain extra rows through false positives, but it must never remove a matching row. A semantic proxy, approximate embedding filter, or ANN index may lose valid candidates. Therefore, the contract changes from exact correctness to an explicit error budget:

~~~text
recall(plan) >= target_recall
quality(plan) >= target_quality
p99_latency(plan) <= SLO
memory(plan) <= budget
~~~

This is the most important conceptual extension from your existing work. Do not describe semantic filtering as if it were automatically equivalent to a Bloom filter.

### 3.3 Resource Bottleneck Reasoning

**CPU-bound path**

- Reduce hash, distance, parsing, and dispatch instructions.
- Use vectorized batches, SIMD leaf kernels, and selection vectors.
- Avoid per-record object allocation and unpredictable branches.
- Ensure that a proxy filter is cheaper than the work it removes.

**Memory-bound path**

- Budget Bloom filters, bitmaps, HNSW edges, PQ codes, caches, and state.
- Measure bandwidth and last-level cache misses, not only allocated bytes.
- Partition or spill when state exceeds budget.
- Avoid false sharing and account for NUMA placement.

**I/O-bound path**

- Push pruning to segment, file, page, or SSD graph traversal.
- Batch and coalesce requests; overlap I/O, decode, and compute.
- Measure bytes and IOPS saved, not only operator CPU time.
- Inspect p99 per-shard and per-rank behavior because one straggler can gate the job.

**Network-bound path**

- Model collective topology, remote fetches, and cross-shard fan-out.
- Reduce synchronization and preserve locality.
- Use bounded concurrency and backpressure.
- Include serialization and state-transfer cost.

**GPU-bound path**

- Compare queueing, transfer, kernel, and synchronization end to end.
- Batch enough to amortize launch cost without violating tail SLOs.
- Keep adjacent operators resident on the device where possible.
- Retain a CPU fallback for small or divergent work.

### 3.4 How to Describe Your Project

Use this structure:

> The problem was that multiway joins generated unnecessary scan and intermediate work. The design constraint was that filters had a memory budget and strict dependency and outer-join semantics. I planned semijoin-style reductions in the optimizer and implemented budgeted runtime filtering in the vectorized engine. I compared exact sets, bitmaps, Bloom filters, and no-filter fallbacks under varying NDV, selectivity, skew, and arrival time. I validated bare-query correctness and measured end-to-end latency, bytes scanned, CPU cycles, and peak memory. The optimization could regress under high selectivity or late arrival, so I added cost gating and runtime fallback.

---

## 4. Multimodal Data Management and Semantic Query Processing

### 4.1 One Algebra, Different Semantic Contracts

A unified system should represent at least:

~~~text
RelationalScan(table, snapshot)
TextSearch(corpus, query, scoring_model)
VectorSearch(index, embedding, k, recall_target)
SemanticMap(input, instruction, output_schema)
SemanticFilter(input, predicate, quality_target)
SemanticJoin(left, right, instruction, quality_target)
SemanticAggregate(input, instruction)
LLMReason(context, task, model_policy)
~~~

The operators cannot all be optimized with ordinary relational equivalence:

- SQL predicates are usually deterministic and exact.
- Full-text ranking is deterministic for a fixed index but score scales differ across retrievers.
- ANN is approximate and recall-bounded.
- LLM/VLM operators are model-, prompt-, and version-dependent, and may be stochastic.
- Agent tool calls may have side effects and therefore cannot be reordered freely.

The optimizer needs an operator contract containing:

- input and output types;
- determinism and side effects;
- selectivity or top-k behavior;
- latency and batch curves;
- monetary and energy cost;
- recall or semantic-quality estimate;
- model, prompt, index, and data versions;
- cacheability and provenance requirements.

### 4.2 Key Literature

[LOTUS](https://www.vldb.org/pvldb/vol18/p4171-patel.pdf) treats semantic filter, join, similarity join, top-k, grouping, and aggregation as declarative operators and defines quality-aware optimized implementations. [Palimpzest](https://www.vldb.org/cidrdb/2025/palimpzest-optimizing-ai-powered-analytics-with-declarative-query-processing.html) searches over models, prompts, and execution methods while balancing runtime, money, and quality.

[CAESURA](https://vldb.org/cidrdb/2024/caesura-language-models-as-multi-modal-query-planners.html) explores language-model-driven plans across arbitrary modalities. [AOP](https://www.vldb.org/cidrdb/papers/2025/p32-wang.pdf) organizes complex data-lake questions through semantic operators and pipeline orchestration. [The Design of an LLM-powered Unstructured Analytics System](https://www.vldb.org/cidrdb/papers/2025/p13-anderson.pdf) describes declarative plans, lineage, and execution history for unstructured analytics.

[SingleStore-V](https://www.vldb.org/pvldb/vol17/p3772-chen.pdf) is a strong production-oriented reference for integrated vector, relational, full-text, filtering, joining, transactions, and distributed execution. [Beyond Quacking](https://www.vldb.org/pvldb/vol18/p5415-mhedhbi.pdf) demonstrates deep SQL integration of BM25, vector search, fusion, and LLM reranking.

Recent frontier work includes [KathDB](https://www.vldb.org/cidrdb/papers/2026/p14-xiao.pdf), which emphasizes explainability and human-AI collaboration, and [InferF](https://arxiv.org/abs/2511.20489), which factorizes AI/ML inference across joins. Treat recent or preprint work as research direction rather than settled industrial consensus.

### 4.3 A Quality-Aware Cost Model

A useful objective is:

~~~text
J(plan) =
    lambda_latency * p95_latency
  + lambda_money   * monetary_cost
  + lambda_gpu     * gpu_seconds
  + lambda_io      * bytes_read
  + lambda_energy  * joules
  + lambda_quality * quality_loss

subject to:
  recall_at_k >= R_min
  semantic_quality >= Q_min
  p99_latency <= SLO
  peak_memory <= budget
~~~

Features should include:

- relational cardinality, NDV, width, and correlation;
- semantic selectivity and proxy-oracle disagreement;
- input/output token distributions;
- model-specific batch and queueing curves;
- cache hit rates and shared prompt prefixes;
- CPU-GPU transfer and remote storage cost;
- vector index recall, probe count, and reranking work;
- data, embedding, prompt, and model versions.

Sampling is essential because semantic selectivity and output length are difficult to estimate statically. A robust optimizer can execute a small sample, update posterior estimates, and choose whether to reorder operators, change the model cascade, or stop an expensive plan.

### 4.4 A Strong Physical Plan

For a query combining SQL, BM25, vector search, and an LLM predicate:

1. Push safe and selective scalar predicates.
2. Run lexical and dense candidate generators, possibly in parallel.
3. Merge candidate streams adaptively rather than using a fixed oversampling constant.
4. Delay wide-column and multimodal payload reads until row IDs survive.
5. Deduplicate repeated semantic inputs.
6. Use a cheap proxy or small model before the expensive LLM/VLM.
7. Batch model calls by model, prompt prefix, and input length.
8. Validate outputs where deterministic checks exist.
9. Attach data, index, prompt, and model lineage to the result.

Do not assume that conventional pushdown is always quality-preserving. Removing context before an LLM operator may reduce calls but lower semantic quality. The optimizer must treat quality as part of rewrite validity.

### 4.5 Caching and Reuse

Separate:

1. **Exact result cache:** key by normalized task, input or snapshot, model/version, system prompt, sampling, retrieved context, tool versions, tenant, and permissions.
2. **Embedding cache:** key by normalized input, preprocessing, model/version, and embedding dimension.
3. **Prefix/KV cache:** reuse only causally valid shared prefixes.
4. **Operator-result cache:** cache semantic maps, classifications, and candidate pairs with dependency-aware invalidation.
5. **Factorized inference cache:** compute a model result once per repeated join value rather than once per materialized output row.

Non-deterministic sampling, changed permissions, re-embedding, model upgrades, and data updates require explicit invalidation rules.

---

## 5. Cloud-Native Vector Retrieval

### 5.1 What Must Be Optimized

Vector search is not a single index benchmark. A production system jointly optimizes:

- recall@k or nDCG;
- p50, p95, and p99 latency;
- QPS and cost per query;
- memory and storage per vector;
- bytes and IOPS per query;
- index build and recovery time;
- update visibility lag;
- rebalance and compaction interference;
- hybrid-filter selectivity and correlation;
- availability and tenant isolation.

Exact search provides a correctness baseline but scales linearly with vectors and dimensions. ANN introduces a controlled quality-performance tradeoff.

### 5.2 Index Families

| Family | Strength | Limitation | Typical placement |
|---|---|---|---|
| HNSW/graph | High recall and low latency | Memory-heavy, difficult updates/rebalance | DRAM or GPU HBM |
| IVF | Easy partitioning and batching | Depends on clustering and probe count | DRAM plus SSD postings |
| Product quantization | Low memory and bandwidth | Distance error, rerank needed | Memory-resident codes |
| SSD graph | Billion-scale at lower DRAM cost | Irregular random I/O | SSD plus compressed memory state |
| Segment plus mutable delta | Simple snapshots and ingestion | Multi-index query and compaction | Cloud-native engines |

[DiskANN](https://proceedings.neurips.cc/paper_files/paper/2019/hash/09853c7fb1d3f8ee67a61b6bf4a7f8e6-Abstract.html) established SSD-resident graph search with compressed in-memory representations. [SPANN](https://proceedings.neurips.cc/paper_files/paper/2021/hash/299dc35e747eb77177d9cea10a802da2-Abstract.html) uses in-memory centroids and disk-resident posting lists. [SPFresh](https://www.microsoft.com/en-us/research/publication/spfresh-incremental-in-place-update-for-billion-scale-vector-search/) adds incremental in-place rebalancing for dynamic billion-scale indexes.

[VBASE](https://www.usenix.org/conference/osdi23/presentation/zhang-qianxi) integrates relational operators and vector search through an incremental candidate interface. [DistVS](https://www.usenix.org/system/files/nsdi26-yin.pdf) studies compute-memory disaggregation, RDMA I/O batching, asynchronous execution, and decoupled reranking. [FlowANN](https://www.usenix.org/conference/osdi26/presentation/zhao) is a 2026 frontier example of CPU-GPU tiering and pipelined graph dependencies.

### 5.3 Distributed Design

Two basic sharding choices:

- **Hash sharding:** simple balance and updates, but queries may fan out to all shards.
- **Semantic or centroid sharding:** fewer shards per query, but routing errors, hot clusters, and distribution drift affect recall and balance.

A practical engine often combines coarse semantic routing with bounded multi-shard search and a fallback.

~~~text
query embedding
    -> router and filter planner
    -> selected shards and replicas
    -> local ANN with per-shard budget
    -> global merge
    -> exact or high-quality rerank
    -> top-k with provenance
~~~

End-to-end tail latency is approximately:

~~~text
p99 ~= routing + max(selected_shard_latency) + merge + rerank
~~~

Therefore, adding replicas or shards can improve average capacity while worsening the maximum-tail term if routing is poor.

The design must address:

- per-shard recall-budget calibration;
- hot-shard detection and replica routing;
- embedding/index version consistency;
- mutable delta and immutable segment visibility;
- background re-embedding and rebuild;
- degraded operation during shard loss;
- tenant quotas and noisy-neighbor isolation.

### 5.4 Filtered Vector Search

The main strategies are:

- **Pre-filter:** compute exact eligible IDs first, then search. Good for selective bitmap-friendly predicates, but the induced graph may lose connectivity.
- **Post-filter:** search first, discard invalid results, and oversample. Simple but may return fewer than k and wastes distance/I/O work.
- **In-index filter:** test eligibility during traversal. Reduces wasted work but can trap search at low selectivity.
- **Workload-specific subindexes:** trade memory and workload dependence for stable filtered performance.

[SIEVE](https://www.vldb.org/pvldb/vol18/p4723-li.pdf) is particularly relevant because it builds a workload-aware collection of indexes and models memory, recall, and search-time tradeoffs.

The key optimizer statistic is not only global scalar selectivity. It is the correlation between the predicate and local vector neighborhoods.

This maps directly to runtime-filter expertise:

- bitmap memory versus probe cost;
- candidate reduction versus construction cost;
- random SSD I/O saved by early filtering;
- adaptive fallback when estimates fail;
- false-positive behavior versus recall-losing false negatives.

### 5.5 Hybrid Lexical and Dense Search

Lexical and dense scores are often not calibrated. [Reciprocal Rank Fusion](https://research.google/pubs/reciprocal-rank-fusion-outperforms-condorcet-and-individual-rank-learning-methods/) combines ranks rather than raw scores:

~~~text
RRF(document) = sum_j 1 / (c + rank_j(document))
~~~

Weighted score fusion can use finer information but requires calibration across query types and index versions. RRF is robust but ignores score margins. A learned reranker may improve quality but adds cost and versioning complexity.

Avoid the naive fixed-K plan:

~~~text
take K lexical + take K vector -> union -> rerank
~~~

The needed oversampling depends on filter-vector correlation, score distributions, and the fusion rule. Prefer iterative candidate streams with an early-termination condition.

---

## 6. Text-to-SQL and Data Agents

### 6.1 Benchmark Progression

- [Spider](https://aclanthology.org/D18-1425/) introduced cross-domain schema generalization.
- [BIRD](https://proceedings.neurips.cc/paper_files/paper/2023/hash/83fc8fab1710363050bbd1d4b8cc0021-Abstract-Datasets_and_Benchmarks.html) added larger databases, values, and domain knowledge.
- [Spider 2.0](https://proceedings.iclr.cc/paper_files/paper/2025/hash/46c10f6c8ea5aa6f267bcdabcb123f97-Abstract-Conference.html) evaluates enterprise workflows with large schemas, multiple dialects, metadata search, and multi-query tasks.
- [InfiAgent-DABench](https://proceedings.mlr.press/v235/hu24s.html) evaluates end-to-end data-analysis agents in an execution environment.

Strong results on Spider 1.0 do not establish enterprise readiness. Real tasks may require dialect documentation, business definitions, multiple SQL statements, data transformation, and clarification.

### 6.2 Production Architecture

~~~text
user intent
  -> authentication and accessible-schema boundary
  -> metadata/business-term retrieval
  -> schema and value grounding
  -> clarification when ambiguous
  -> logical analytical plan
  -> constrained SQL candidates
  -> parse, bind, and plan inspection
  -> read-only bounded execution
  -> semantic and result verification
  -> answer with assumptions, SQL, and provenance
~~~

[PICARD](https://aclanthology.org/2021.emnlp-main.779/) incrementally rejects syntactically invalid tokens. It improves validity but does not prove the query answers the intended business question.

[OmniSQL](https://www.vldb.org/pvldb/vol18/p4695-li.pdf) is relevant for large-scale synthetic training data and model development. [Database-Free Text-to-SQL Evaluation](https://aclanthology.org/2025.coling-main.308/) represents plans as graphs to estimate functional equivalence. [Graph-Reward-SQL](https://aclanthology.org/2025.findings-emnlp.694/) uses graph-based outcome and stepwise rewards without repeatedly executing full queries.

### 6.3 Verification

Execution success is not correctness:

- two equivalent queries may have different syntax;
- two different queries may coincidentally return the same result on one database;
- test data may not distinguish NULL, duplicate, boundary, aggregation, or join errors;
- a syntactically valid query may use the wrong business definition.

Combine:

- parser, binder, and type checks;
- access-control and resource checks;
- logical-plan or graph comparison;
- generated distinguishing databases or metamorphic tests;
- result-shape and business invariants;
- multiple candidate comparison;
- expert review for high-risk workflows.

Every execution should be read-only by default, with limits on time, scanned bytes, rows, concurrency, and external tools.

---

## 7. Network and Observability for AI Clusters

### 7.1 Why Ordinary Monitoring Is Insufficient

Large training jobs have collective synchronization. One slow or failed rank can stall thousands of healthy ranks. The root cause may be:

- user code or data-loader skew;
- CPU starvation or memory pressure;
- GPU kernel, clock, thermal, ECC, or silent corruption;
- NVLink/NVSwitch or PCIe degradation;
- NCCL, RDMA, NIC, link, or switch problems;
- storage or checkpoint delay.

The failed process may stop emitting evidence, while healthy ranks produce many timeout messages. Correlation without topology can blame victims instead of the culprit.

Distinguish:

1. anomaly detection;
2. component or rank localization;
3. root-cause mechanism;
4. safe remediation.

### 7.2 Three Joined Graphs

A production design should join:

- **Logical execution graph:** iteration, operator, collective, rank, DP/TP/PP/EP groups.
- **Physical topology graph:** host, GPU, NVLink, PCIe, NIC, ToR, spine, storage endpoint.
- **Software graph:** framework, CUDA kernel, NCCL operation, driver, filesystem, storage RPC.

Stable correlation identifiers include:

~~~text
cluster, job, attempt, iteration, rank, collective,
operator, host, GPU, NIC, route version, topology version
~~~

Use:

- metrics for continuous SLO and health;
- structured logs for discrete state transitions;
- traces for causality and critical paths;
- profiles for targeted investigations;
- local ring buffers for high-fidelity evidence exported after an anomaly.

### 7.3 Diagnosis Pipeline

~~~text
GPU/NIC/framework agents
       -> local aggregation and sketches
       -> rack/regional collectors
       -> hot TSDB plus trace/log stores
       -> anomaly and topology-aware RCA
       -> targeted validation
       -> bounded remediation and verification
~~~

Useful techniques:

- compare equivalent ranks in the same collective;
- compare the same rank across iterations;
- find missing progress, not only emitted errors;
- retain tail distributions rather than per-rank means;
- use active GPU, network, and storage tests for ambiguous gray failures;
- rank suspects with confidence and supporting evidence;
- confirm before disruptive actions.

[MegaScale](https://www.usenix.org/conference/nsdi24/presentation/jiang-ziheng) is essential role-specific reading for full-stack training efficiency, observability, failures, and stragglers at more than 10,000 GPUs. [FLARE](https://www.usenix.org/conference/nsdi26/presentation/cui) provides full-stack tracing and anomaly diagnosis. [EROICA](https://www.usenix.org/conference/nsdi26/presentation/guan-yu) uses fine-grained online profiling and differential observability. [SDCHunter](https://www.usenix.org/conference/osdi26/presentation/zheng) studies workload-dependent silent data corruption and replay-based diagnosis.

### 7.4 Time-Series Infrastructure

AI observability creates extreme series cardinality across jobs, ranks, operators, collectives, and devices. A TSDB needs:

- WAL-backed ingestion;
- time and series partitioning;
- timestamp and value compression;
- immutable blocks and background compaction;
- hot recent data plus durable cold storage;
- tag indexes with cardinality controls;
- recording rules, retention classes, and downsampling;
- quotas, fan-out control, and admission control.

Approximate capacity:

~~~text
storage =
  samples_per_second
  * retention_seconds
  * bytes_per_sample
  * replication
  + WAL/index/compaction headroom
~~~

[Gorilla](https://www.vldb.org/pvldb/vol8/p1816-teller.pdf) is foundational for compressed, highly available recent monitoring data. [BTrDB](https://www.usenix.org/conference/fast16/technical-sessions/presentation/andersen) explores versioned time-series storage and statistical range queries. [Monarch](https://research.google/pubs/monarch-googles-planet-scale-in-memory-time-series-database/) is useful for planet-scale multi-tenant monitoring architecture.

An intelligent TSDB tuner may adjust shard count, block duration, WAL batching, cache division, compaction concurrency, query parallelism, retention, and roll-up. It must use canaries and rollback because the monitored system supplies the tuner's own feedback.

Evaluation metrics:

- top-k culprit accuracy and calibration;
- detection and localization time;
- false-positive rate;
- telemetry volume and runtime overhead;
- mean time to recovery;
- GPU-hours saved;
- incident recurrence after remediation.

---

## 8. Serverless AI Storage and DPU Co-Design

### 8.1 Separate the Workloads

| Workload | Access pattern | Critical metric |
|---|---|---|
| Training input | Many shuffled samples, metadata-heavy | Samples/s without GPU starvation |
| Checkpoint | Synchronized large writes and later resharded reads | Training pause and recovery time |
| Model deployment | Large bursty reads to many replicas | Cold-start p99 |
| Vector index | Random metadata and graph/posting reads | Recall, bytes/query, p99 |
| Inference state | KV/context reuse and spill | TTFT/TPOT and capacity |

More storage bandwidth does not help if decoding, tokenization, or host-to-device transfer is the real bottleneck:

~~~text
input_rate <= min(
  storage_bandwidth / mean_sample_size,
  network_bandwidth / mean_sample_size,
  decode_rate,
  transform_rate,
  gpu_consumption_rate
)
~~~

### 8.2 Elastic Storage Architecture

~~~text
durable object or replicated-SSD tier
        |
transactional metadata authority
        |
elastic metadata/data services
        |
distributed flash cache + node-local NVMe/DRAM
        |
POSIX compatibility client + native high-performance client
~~~

Key rules:

- keep authoritative state durable and functions stateless where possible;
- cache immutable datasets aggressively;
- detect hot namespaces and training-launch thundering herds;
- scale CPU, memory, IOPS, bandwidth, and metadata capacity jointly;
- prewarm predictable model and dataset launches;
- use tenant admission control and bounded in-flight bytes;
- make retries idempotent.

[Pocket](https://www.usenix.org/conference/osdi18/presentation/klimovic) shows multi-resource rightsizing for elastic ephemeral storage. [Tectonic](https://www.usenix.org/conference/fast21/presentation/pan) is a reference for exabyte-scale multitenant filesystem design. [ServerlessLLM](https://www.usenix.org/conference/osdi24/presentation/fu) treats model loading and locality as scheduling inputs.

### 8.3 Checkpoint Correctness and Performance

A safe publication protocol:

1. write versioned shards to temporary immutable names;
2. verify size and checksums;
3. ensure all required shards are durable;
4. atomically publish one manifest;
5. let readers consume only committed manifests;
6. keep retries idempotent.

Reduce the critical pause by copying GPU state into pinned host memory or local NVMe, then persist in the background. Deduplicate replicated tensors, balance writes, and reshard during load.

[ByteCheckpoint](https://www.usenix.org/conference/nsdi25/presentation/wan-borui) is particularly important because it is a ByteDance industrial system covering parallelism-agnostic representation, load-time resharding, multiple frameworks/backends, full-stack I/O optimization, and monitoring.

The classical first-order checkpoint interval is:

~~~text
optimal_interval ~= sqrt(2 * checkpoint_time * job_MTBF)
~~~

At larger cluster scale, job MTBF falls, so reducing checkpoint pause and recovery cost becomes more valuable.

### 8.4 DPU and Direct Data Paths

Good DPU candidates are frequent fast-path operations with bounded state:

- transport, batching, DMA, and virtual device handling;
- NVMe-oF or object-client processing;
- checksums, encryption, compression, and erasure-code primitives;
- replication, QoS, and telemetry;
- direct DPU-to-GPU movement.

Keep complex placement, policy, recovery, and rare control operations on the host.

~~~text
Host control plane:
  placement, policy, recovery, rare operations

DPU data plane:
  transport, DMA, batching, checksum/compression,
  replication, QoS, fast-path cache

GPU:
  decode, preprocessing, vector distance, or model compute
~~~

[Characterizing Off-path SmartNIC](https://www.usenix.org/system/files/osdi23-wei-smartnic.pdf) shows why communication paths and constrained onboard resources matter. [NVIDIA GPUDirect Storage](https://docs.nvidia.com/gpudirect-storage/overview-guide/index.html) documents direct storage-to-GPU DMA that avoids CPU bounce buffers. Direct is not automatically faster:

~~~text
path_latency =
  host_to_DPU
  + DPU_compute
  + DPU_to_network_or_storage_or_GPU
~~~

Measure host cores saved, GPU utilization, p99 latency, throughput per watt, and behavior under DPU or host failure, not only a DPU microbenchmark.

### 8.5 Diagnosing an Input Bottleneck

1. Confirm GPU starvation using step timelines and input-queue occupancy.
2. Compare required and achieved rates at metadata, read, network, decode, transform, and transfer stages.
3. Compare RAM-backed, cached, and uncached datasets.
4. Disable or simplify transformations to isolate preprocessing.
5. Inspect open/stat latency and small-read distributions.
6. Inspect per-rank tails, not aggregate bandwidth.
7. change locality, concurrency, and record packing one variable at a time.
8. Optimize the first saturated stage, then repeat.

---

## 9. Heterogeneous CPU/GPU/MEM and Power Scheduling

### 9.1 Optimize Useful Progress

GPU utilization is not the objective. A job can report high utilization while making poor statistical progress, violating inference latency, or wasting energy.

For training:

~~~text
goodput = system_throughput * statistical_efficiency
~~~

For inference:

~~~text
goodput = requests_per_second that satisfy TTFT and TPOT SLOs
~~~

A general objective:

~~~text
minimize over placements:
  resource_cost
  + lambda_slo * SLO_penalty
  + lambda_move * state_transition_cost
  + lambda_energy * energy

subject to:
  CPU, GPU, HBM, DRAM, network, storage, rack-power capacity
  accelerator compatibility and topology
  gang and DAG dependencies
  tenant quota and fairness
  chance constraints under prediction uncertainty
~~~

### 9.2 Literature Progression

[Dominant Resource Fairness](https://www.usenix.org/conference/nsdi11/dominant-resource-fairness-fair-allocation-multiple-resource-types) is the classical multi-resource fairness baseline. [Themis](https://www.usenix.org/conference/nsdi20/presentation/mahajan) introduces finish-time fairness for GPU jobs. [Pollux](https://www.usenix.org/conference/osdi21/presentation/qiao) jointly adapts training configuration and cluster resources using goodput.

[Synergy](https://www.usenix.org/conference/osdi22/presentation/mohan) directly addresses GPU/CPU/MEM sensitivity and shows why GPU-proportional host allocation wastes resources. [Sia](https://doi.org/10.1145/3600006.3613175) combines heterogeneous accelerator selection with elastic training. [MLaaS in the Wild](https://www.usenix.org/conference/nsdi22/presentation/weng) provides production trace evidence about low utilization, queueing, heterogeneous GPUs, and CPU bottlenecks.

[Zeus](https://www.usenix.org/conference/nsdi23/presentation/you) studies the performance-energy frontier using batch size and GPU power limits. The lesson is that maximum power and maximum throughput need not minimize energy or cost.

### 9.3 State and Dependency Costs

Separate:

1. precedence dependencies in training or agent DAGs;
2. data and state locality for weights, checkpoints, vector indexes, and KV cache;
3. gang and collective dependencies among workers;
4. external side effects from agent tools.

Resize only when:

~~~text
expected benefit over remaining horizon >
  checkpoint + transfer + restart + warmup + transient SLO cost
~~~

Use consistency boundaries, versioned state, leases or epochs, hysteresis, and a minimum dwell time.

[Llumnix](https://www.usenix.org/conference/osdi24/presentation/sun-biao) demonstrates live migration of LLM requests and KV state. [DistServe](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin) separates prefill and decode, making topology and state transfer explicit scheduling inputs.

### 9.4 Two-Timescale Power Control

Use:

- a fast local loop for cap enforcement, thermal safety, and emergency throttling;
- a slower global loop for placement, power allocation, and headroom;
- SLO-aware degradation that protects interactive work before best-effort jobs;
- conservative margins for telemetry delay and migration transients.

Metrics include:

- mean and p99 job completion;
- SLO-attaining goodput;
- fairness and starvation;
- cost and joules per useful unit;
- rack-power violations;
- scheduler decision time;
- migration and checkpoint overhead;
- performance under stale telemetry and failed actuators.

---

## 10. AI for Infrastructure and Safe Self-Evolving Agents

### 10.1 A Guarded Control Loop

An LLM should not directly own unconstrained actuation:

~~~text
telemetry
  -> statistical/ML predictors
  -> LLM diagnosis and planning
  -> deterministic policy validator
  -> constrained optimizer
  -> rate-limited actuator
  -> outcome verifier
  -> rollback or promotion
~~~

Use the right mechanism for each responsibility:

- rules and formal constraints for hard safety;
- classical optimization for feasible resource allocation;
- ML for latency, workload, and fault prediction;
- LLM agents for cross-domain diagnosis, explanation, and tool orchestration.

[Bao](https://arxiv.org/abs/2004.03814) is a useful pattern: learning steers a mature optimizer through bounded choices rather than replacing its correctness mechanisms. [Balsa](https://arxiv.org/abs/2201.01441) explores learning a query optimizer without expert demonstrations. [Lero](https://www.vldb.org/pvldb/vol16/p1466-zhu.pdf) learns pairwise plan ranking. [Eraser](https://www.vldb.org/pvldb/vol17/p926-zhu.pdf) explicitly addresses performance regressions in learned query optimization.

### 10.2 Agent Loop and Evaluation

[ReAct](https://arxiv.org/abs/2210.03629) supplies the observe-reason-act structure. [Reflexion](https://papers.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html) stores verbal feedback from prior attempts. [SWE-agent](https://proceedings.neurips.cc/paper_files/paper/2024/hash/5a7c947568c1b1328ccc5230172e1e7c-Abstract-Conference.html) shows that the agent-computer interface materially affects performance.

Infrastructure evaluation must test more than task completion:

- diagnosis accuracy and calibration;
- unsafe-action rate;
- remediation success and rollback rate;
- SLO and cost impact;
- tool-call and token cost;
- performance under unseen versions and topology;
- prompt injection and poisoned telemetry;
- human override and auditability.

[AIOpsLab](https://proceedings.mlsys.org/paper_files/paper/2025/hash/d1f9e4a9f109b6e8b75ed362736f22ec-Abstract-Conference.html) provides deployable cloud environments, workloads, telemetry, and fault injection for operational-agent evaluation. [ToolEmu](https://proceedings.iclr.cc/paper_files/paper/2024/hash/7274ed909a312d4d869cc328ad1c5f04-Abstract-Conference.html) and [AgentDojo](https://proceedings.nips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html) emphasize tool-use risk and prompt injection.

### 10.3 Auto Skills as Versioned Artifacts

A production skill should contain:

- typed inputs and outputs;
- preconditions and postconditions;
- least-privilege permissions;
- valid software, hardware, and topology versions;
- source trajectories and provenance;
- deterministic and hidden tests;
- action budget, timeout, and rollback;
- semantic version and signed approval.

A safe evolution process:

1. store immutable, provenance-tagged experience;
2. create a new candidate skill version;
3. run static and policy checks;
4. replay historical incidents and inject faults;
5. execute in read-only or shadow mode;
6. canary on a bounded scope;
7. promote only through SLO, safety, and cost gates;
8. monitor and roll back automatically.

[MUSE-Autoskill](https://arxiv.org/abs/2605.27366) is a 2026 preprint closely aligned with the JD's Auto Skills language. It should be read as frontier work, not as established production proof.

Knowledge precedence should be explicit:

~~~text
immutable safety policy
  > verified operational runbook
  > promoted skill
  > validated episodic evidence
  > unverified observation
~~~

---

## 11. Candidate Mapping and Research Agenda

### 11.1 Honest Fit Matrix

| JD direction | Current evidence | Transfer argument | Preparation priority |
|---|---|---|---|
| Multimodal query processing | Query evaluation, join optimization, Yannakakis+ | Semantic operators still need algebra, candidate reduction, costing, and execution | Highest |
| Distributed vector retrieval | Runtime filters and CPU/memory/I/O analysis | Filtered ANN is a cross-layer pruning problem with recall constraints | Highest |
| Text-to-SQL and data agents | Optimizer and plan semantics | Can contribute plan-aware grounding, verification, and safe execution | High |
| AI cluster observability | Systems performance diagnosis | Bottleneck localization transfers, but collective communication is new | High gap-closing |
| Serverless AI storage and DPU | I/O-bound optimization | Data-path analysis transfers; hardware offload experience must not be overstated | High gap-closing |
| CPU/GPU/MEM and power scheduling | Resource bottleneck reasoning | Cost models and adaptive execution transfer; cluster control is new | Medium-high |
| AI for infrastructure | Query optimization and runtime feedback | Strong basis for bounded learned decisions and verification | High |

The strongest application strategy is a T-shaped profile: demonstrate research depth in query processing and credible breadth across the remaining infrastructure layers. Do not claim that reading several papers is equivalent to building a 10,000-GPU cluster. Instead, explain which principles transfer, which facts you have verified, and what experiment you would run next.

### 11.2 Three Research Proposals

#### Proposal A: Quality-Bounded Yannakakis for Semantic Joins

**Problem.** A workflow may join structured relations and then apply expensive semantic predicates to text, image, or document pairs. Materializing the relational join first can repeat the same model inference and create a quadratic candidate space.

**Idea.** Represent semantic predicates as quality-bounded filters or verifiers. Use exact semijoin reductions first, cache inference by distinct values, generate candidates with embeddings or a small model, and invoke a larger LLM/VLM only on uncertain survivors. Apply factorization when inference depends on a subset of join attributes.

**Optimizer state.** Track relation cardinalities, distinct values, join dependency structure, proxy selectivity, proxy-oracle disagreement, batch curves, prompt tokens, and cache reuse.

**Guarantee.** Exact relational reductions preserve correctness. Approximate semantic reductions consume an explicit false-negative or recall budget, estimated with confidence intervals and guarded by fallback sampling.

**Evaluation.** Compare against join-then-infer, hand-written cascades, and conventional binary plans. Measure end-to-end quality, model calls, GPU seconds, p99 latency, bytes moved, and peak memory. Ablate factorization, semijoin rounds, proxy choice, caching, and adaptive fallback.

#### Proposal B: Adaptive Runtime Filters for Hybrid SQL and ANN

**Problem.** Filtered vector search behaves poorly when the scalar predicate's global selectivity does not describe its local correlation with vector neighborhoods. A single pre-filter, post-filter, or in-index strategy is not robust.

**Idea.** Build an adaptive operator that observes eligible-density along the ANN traversal, candidate yield, bitmap locality, SSD queue depth, and distance-computation rate. It switches among bitmap-guided traversal, post-filter oversampling, workload-specific subindexes, and exact scan fallback.

**Cost model.** Include filter build and broadcast, bitmap bytes, CPU distance work, random I/O, cross-shard tail, global merge, and recall loss. Re-optimize when observed candidate yield diverges from the estimate.

**Evaluation.** Use synthetic and production-like workloads that independently vary selectivity, neighborhood correlation, skew, update rate, memory budget, and shard imbalance. Report recall@k and nDCG together with p50/p99 latency, QPS, bytes/query, and cost/query.

#### Proposal C: Verified AI Control for Query and Infrastructure Tuning

**Problem.** An LLM can synthesize plausible tuning actions but may hallucinate a knob, ignore a hidden dependency, or react to poisoned telemetry.

**Idea.** Let the agent retrieve evidence and propose a typed action plan. A deterministic validator checks permissions, preconditions, invariants, risk budgets, and rollback. A constrained optimizer selects a feasible action. Execution proceeds through replay, shadow, canary, and bounded rollout.

**Learning loop.** Store immutable incident evidence and outcome-labeled trajectories. New skills are derived as candidates, evaluated on versioned environments, and promoted rather than modifying production skills in place.

**Evaluation.** Measure diagnosis top-k accuracy, unsafe-action rate, false rollback rate, MTTR, SLO impact, cost saved, tool calls, and robustness to version drift, missing telemetry, and prompt injection.

### 11.3 How to Describe Existing Work

Use a five-part research story:

1. **Problem:** state the workload and why the existing optimizer or executor wastes work.
2. **Invariant:** explain the semantic property that permits a reduction or reordering.
3. **Mechanism:** show the optimizer rule, runtime operator, data structure, and pipeline dependency.
4. **Resource result:** separate CPU, memory, I/O, and network effects rather than reporting only latency.
5. **Boundary:** identify the workload where the technique loses and the fallback that protects performance.

A useful two-minute version is:

> I studied how to reduce intermediate work in join evaluation using Yannakakis-style reasoning and runtime filters. The central invariant is that a tuple that cannot join downstream can be removed before expensive materialization. I translated that into optimizer and execution changes, then analyzed the filter as a resource tradeoff: build cost and memory versus saved scan I/O, probe CPU, join work, and network traffic. The important result was not that filters always win, but that their value depends on selectivity, arrival time, cardinality uncertainty, and the active bottleneck. This is directly relevant to AI-native queries, where an embedding or small model can reduce expensive LLM work, but unlike a Bloom filter it may create false negatives and therefore needs an explicit quality budget.

### 11.4 Resume and Research-Statement Language

Use evidence-bearing bullets, for example:

- Designed and implemented [optimizer/executor component] for [join or runtime-filter problem], preserving [correctness invariant] across [join classes or execution modes].
- Reduced [bytes read / intermediate rows / CPU cycles / peak memory] by [measured amount] on [workload], yielding [latency or throughput result] against [named baseline].
- Built a resource-aware decision rule using [cardinality, NDV, filter size, selectivity, or pipeline timing], with fallback for [skew, late filters, memory pressure, or bad estimates].
- Diagnosed CPU-, memory-, and I/O-bound regimes using [profiles and counters], and validated causality with [controlled ablation].

Avoid unsupported claims such as "built an AI-native database" if the evidence is a query-optimizer prototype. Precise scope creates more confidence than broad wording.

### 11.5 Evidence Package Before the Interview

Prepare the following artifacts:

- a one-page diagram of the optimizer and execution path;
- one query plan before and after the change;
- one table separating CPU, memory, I/O, and end-to-end metrics;
- one negative result and the design change it caused;
- one correctness test involving nulls, duplicates, outer joins, or skew;
- one experiment showing when a runtime filter should be disabled;
- one slide mapping the same pruning principle to semantic joins and filtered ANN;
- concise ownership boundaries: what you designed, implemented, evaluated, and wrote.

---

## 12. Interview Question Bank with Model Answers

These are model structures, not scripts. Replace bracketed evidence with your real results and keep the first answer to roughly 60-90 seconds unless the interviewer asks for depth.

### A. Research Identity and Query Processing

#### Q1. Tell me about your research and why it fits this role.

**Model answer.** My work focuses on query evaluation and optimization, especially eliminating tuples and work before expensive joins or materialization. I have studied Yannakakis-style reductions and runtime filters, including their CPU, memory, and I/O tradeoffs. The fit is strongest in multimodal query processing and distributed vector retrieval: AI-native operators make downstream work much more expensive, so candidate reduction, factorization, adaptive costing, and execution placement become even more important. The extension I want to study is quality-bounded pruning, because semantic proxies can create false negatives whereas a classical Bloom filter cannot.

#### Q2. Explain Yannakakis' algorithm and its assumptions.

**Model answer.** For an acyclic conjunctive query, construct a join tree. A bottom-up semijoin pass removes child tuples that cannot match their parent; a top-down pass removes parent tuples that cannot participate with each child. The final joins operate on reduced relations and avoid large dangling-tuple intermediates. The guarantee depends on acyclicity and correct semijoin propagation. In implementation I would also discuss duplicate semantics, null behavior, projection requirements, and synchronization between reduction phases.

#### Q3. What changes for cyclic joins?

**Model answer.** A join tree no longer captures all constraints, so two semijoin passes do not generally produce a globally reduced database. Options include hypertree or generalized hypertree decompositions, worst-case optimal joins, variable elimination, or using predicate transfer as a heuristic before a conventional plan. The optimizer should compare width, reduction cost, intermediate bounds, and the mature binary plan rather than applying one technique universally.

#### Q4. When does a runtime filter help, and when can it hurt?

**Model answer.** It helps when the filter arrives early, removes enough rows or bytes, and saves expensive downstream work. It hurts when build or broadcast is costly, selectivity is weak, probes are CPU-heavy, the filter misses the scan window, or its memory displaces more valuable state. I would estimate avoided I/O, CPU, network, and model work, subtract construction and probe costs, enforce a memory budget, and disable or shrink the filter when observed selectivity diverges.

#### Q5. How do you size a Bloom filter?

**Model answer.** For n inserted items and m bits with k hash functions, the false-positive probability is approximately (1 - exp(-kn/m))^k. The optimum k is (m/n) ln 2, and bits per item for target probability p are -ln(p)/(ln 2)^2. In a real engine, I cap k because hashes cost CPU, use the actual NDV rather than row count, respect a per-filter memory budget, and compare expected false-positive work with an exact set, bitmap, or no-filter fallback.

#### Q6. How do outer joins complicate semijoin reduction and reordering?

**Model answer.** Outer joins preserve unmatched rows on one side, so removing a row merely because it lacks a match can change the result. Predicate movement also interacts with null introduction and three-valued logic. I would define which side is preserved, prove each reduction against that semantics, and keep join kind relative to child orientation when an optimizer swaps operands. Tests must cover null keys, duplicates, empty inputs, and predicates above and below the outer join.

#### Q7. How would you build a cost model for runtime filtering?

**Model answer.** The model needs build cardinality and NDV, filter bytes, hash count, build and probe CPU, arrival time, scan throughput, selectivity, downstream row cost, network savings, and memory opportunity cost. The benefit is the work avoided after accounting for false positives; the cost includes construction, distribution, probing, stalls, and cache pressure. I would calibrate coefficients from operator-level measurements and add runtime feedback because cardinality and timing errors often dominate static estimates.

#### Q8. How do you diagnose whether an operator is CPU-, memory-, or I/O-bound?

**Model answer.** Start with a pipeline timeline and throughput, then triangulate. CPU-bound work shows saturated cores and useful cycles or branch/SIMD inefficiency; memory-bound work shows bandwidth or cache-miss pressure with weak scaling; I/O-bound work shows device or remote queues, latency, and idle compute. I would change one limiting resource at a time: cached versus uncached input, reduced columns, no-op kernels, altered concurrency, and hot versus cold data. End-to-end latency alone cannot establish causality.

#### Q9. What makes a vectorized executor fast?

**Model answer.** It amortizes interpretation and virtual dispatch over a batch, uses compact selection vectors, keeps data in cache-friendly columnar form, and exposes tight loops to SIMD. It avoids per-tuple allocation and minimizes branches, materialization, and format conversion. The batch size must balance locality, latency, and downstream backpressure. I would preserve scalar fallbacks and benchmark different data distributions, null rates, selectivities, and instruction sets.

#### Q10. How would you evaluate a new optimizer rule convincingly?

**Model answer.** First prove semantic scope and run correctness tests on bare queries, including adversarial null, duplicate, skew, and empty cases. Then compare against the normally optimized baseline on a release build. Report plan-shape coverage, compile time, p50/p99 execution, CPU, memory, bytes read, and regressions, not only geometric-mean speedup. Use ablations for each mechanism and explain the worst cases and fallback policy.

### B. Multimodal Queries and Semantic Operators

#### Q11. Design an execution plan for SQL filters, BM25, vector similarity, and an LLM predicate.

**Model answer.** Represent each as an operator with explicit semantics. Push safe exact predicates, run sparse and dense candidate generators, and fuse their incremental top-k streams rather than taking a fixed K blindly. Fetch wide payloads only for surviving row IDs, then batch a small proxy or the LLM/VLM. Validate exact conditions, preserve provenance and model/index versions, and adapt oversampling from observed candidate yield. Optimize recall and semantic quality together with p99 latency, GPU seconds, and money.

#### Q12. Why is a traditional database cost model insufficient for LLM operators?

**Model answer.** Cardinality is only one driver. Cost depends on prompt and output tokens, model choice, batch shape, queueing, rate limits, cache hits, CPU-GPU transfer, and remote API variance. Rewrites may also change output quality because the model sees different context. I would optimize latency, money, energy, and resource use subject to recall and quality constraints, estimate uncertain quantities by sampling, and re-optimize or fall back when runtime observations disagree.

#### Q13. Can predicate pushdown ever make a semantic query worse?

**Model answer.** Yes. Relational pushdown preserves exact semantics when its preconditions hold, but an LLM predicate may rely on context that the rewrite removes. Pushdown can reduce calls yet lower classification or answer quality. I would define the reference semantics, test proxy-oracle disagreement on samples, preserve context columns when needed, and treat the rewrite as a quality-cost choice rather than an unconditional equivalence.

#### Q14. How can Yannakakis-style ideas accelerate semantic joins?

**Model answer.** First use exact selections and semijoins to reduce base relations. Next generate semantic candidate pairs with lexical rules, embeddings, or a small model; cache by distinct input values; and apply the expensive LLM only as a verifier. If inference depends on one side or a subset of join keys, factor it below the join. The new difficulty is false negatives, so approximate reductions need an explicit recall budget and audit sampling.

#### Q15. How would you cache LLM results inside a database?

**Model answer.** The cache key must include canonicalized input data, prompt template and parameters, model and tokenizer version, tool/schema context, decoding settings, safety policy, and relevant authorization scope. Deterministic or low-temperature functions are easiest to reuse. I would distinguish exact reuse from semantic reuse, attach provenance and expiry, invalidate on data or policy change, isolate tenants, and account for cache lookup and storage in the optimizer.

#### Q16. What is factorized inference?

**Model answer.** It avoids repeating a model computation after a join has duplicated its input. If an inference depends only on attributes from one relation, evaluate it once per distinct value before joining and reuse the result. More generally, decompose inference over a factorized representation when semantics permit. The optimizer compares saved calls with deduplication, materialization, cache, and lost batching costs, and it must prove that moving the operation preserves the intended context.

#### Q17. How would you choose between a small model, a large model, and a cascade?

**Model answer.** Estimate their latency, batch efficiency, financial cost, and error by input region. A small model handles confident easy cases; uncertain cases escalate to the large model. Calibrate confidence against a reference set, set thresholds from the quality budget, monitor drift, and retain random audit traffic. The optimizer should include escalation rate and queue interaction because a cascade can amplify tail latency if many cases become uncertain together.

### C. Vector Retrieval

#### Q18. Compare HNSW, IVF/PQ, and SSD-resident ANN.

**Model answer.** HNSW usually offers strong recall-latency but consumes memory and is difficult to update, snapshot, and rebalance. IVF partitions vectors into posting lists, supports batching and distribution well, and combines naturally with PQ, but depends on clustering and probe count. SSD graph or posting designs reduce DRAM cost but add irregular I/O, so compact in-memory routing, asynchronous reads, batching, and reranking matter. The choice follows recall, update, memory, cost, and p99 requirements.

#### Q19. When should filtered ANN use pre-filtering, post-filtering, or in-index filtering?

**Model answer.** Pre-filtering works for highly selective cheap predicates when an eligible bitmap or exact scan is efficient. Post-filtering works for weak filters when ordinary ANN returns enough valid candidates. In-index filtering avoids some wasted work but can break graph connectivity. Global selectivity is insufficient; local filter-vector correlation determines candidate yield. I would add adaptive oversampling, workload-specific subindexes, and an exact fallback for the difficult middle regime.

#### Q20. How would you build a billion-scale distributed vector service?

**Model answer.** Use a small in-memory routing layer and partition immutable vector segments across shards, with a mutable delta for fresh writes. Store compact codes or routing state in memory and larger postings or graphs on local or disaggregated SSD. Execute local ANN asynchronously, merge top-k streams globally, rerank exact vectors, replicate or erasure-code durable state, and route around slow shards. Evaluate global recall, p99, QPS, memory/vector, bytes/query, update lag, rebuild, rebalance, and failure recovery.

#### Q21. Why is distributed vector-search tail latency difficult?

**Model answer.** A global query often waits for the slowest participating shard, so p99 is roughly routing plus the maximum shard latency plus merge and rerank. Skew, cache misses, SSD queues, network variance, and uneven candidate budgets amplify the tail. I would use selective routing, calibrated per-shard recall budgets, hedging only where its cost is justified, asynchronous early termination, replica-aware routing, and explicit recall accounting when dropping a straggler.

#### Q22. How do online updates affect a vector index?

**Model answer.** Graph mutation can damage neighborhood quality and creates synchronization and snapshot complexity. A common design writes new or changed vectors into a mutable delta, searches base and delta together, then builds immutable segments in the background and atomically swaps a manifest. Tombstones handle deletes until compaction. I would measure visibility lag, query amplification, rebuild cost, recall during churn, and behavior under embedding-version migration.

#### Q23. How would you combine lexical and dense retrieval?

**Model answer.** BM25 and dense scores have different scales, so raw score addition requires calibration. Reciprocal Rank Fusion is a robust rank-only baseline; a learned ranker can do better with training data. The engine should consume incremental candidate streams and stop when unseen candidates cannot enter the final top-k. The evaluation needs lexical, semantic, and mixed intents, with recall/nDCG, latency, candidate count, and reranking cost.

#### Q24. How is a semantic filter different from a Bloom filter?

**Model answer.** A Bloom filter has false positives but, absent implementation errors, no false negatives for inserted keys. Therefore it wastes some downstream work but preserves relational results. A semantic proxy may reject a truly relevant item, so it can change the answer. It needs calibrated uncertainty, an explicit recall or quality budget, validation samples, versioned data/model context, and a fallback path.

### D. Text-to-SQL and Data Agents

#### Q25. Design a production enterprise Text-to-SQL system.

**Model answer.** Authenticate first, retrieve only authorized schema and business metadata, ground terms and values, and clarify ambiguous intent. Generate one or more candidates with grammar and schema constraints, parse and bind them, inspect plans for forbidden or expensive operations, and execute read-only in a bounded sandbox. Use errors and small result summaries for repair. Verify with invariants, differential test data, result-shape expectations, and plan semantics, then return SQL, assumptions, provenance, and an audit trace.

#### Q26. Why are exact match and execution accuracy insufficient?

**Model answer.** Equivalent SQL can differ syntactically, so exact match creates false negatives. Incorrect queries can coincidentally return the same result on one database instance, so execution accuracy creates false positives. Evaluation should combine parse and bind success, plan or relational-graph equivalence, execution on distinguishing databases, business invariants, and human review for ambiguous intent. Production evaluation must also include safety, latency, cost, and clarification quality.

#### Q27. What does PICARD solve, and what does it not solve?

**Model answer.** PICARD constrains autoregressive decoding by incrementally rejecting tokens that cannot lead to syntactically valid SQL. Schema-aware constraints can also reduce invalid identifiers. It does not prove that the query reflects the user's intent, chooses the correct join path, handles business definitions, or is safe and affordable to execute. It belongs inside a broader grounding and verification pipeline.

#### Q28. How would you reduce hallucination in a data-analysis agent?

**Model answer.** Reduce unsupported generation rather than asking the model to remember the enterprise. Retrieve authoritative schema, metric definitions, and sample values under authorization; require tool-backed evidence; use typed tool calls; constrain SQL; execute in a sandbox; validate units, ranges, joins, and aggregates; and cite provenance. Ask clarification when confidence is low, distinguish observation from inference, and never let a fluent narrative override contradictory query results.

#### Q29. What should an Auto Skill contain?

**Model answer.** Treat a skill as a versioned typed artifact: inputs, outputs, preconditions, postconditions, least-privilege permissions, compatible environment versions, source provenance, deterministic and hidden tests, resource budget, timeout, rollback, semantic version, and approval signature. A skill is promoted through static checks, replay, fault injection, shadow, and canary stages. Production versions are immutable and revocable.

#### Q30. How would you evaluate a self-evolving agent safely?

**Model answer.** Separate capability from safety. Test task success, diagnosis quality, tool cost, latency, and generalization, but also unsafe-action rate, policy bypass, prompt injection, poisoned memory, version drift, rollback success, and human override. Use reproducible environments with fault injection and hidden tests. Learning produces candidate skills; deterministic gates decide promotion. Online changes start read-only or in shadow and have bounded blast radius.

### E. AI Cluster Observability, Storage, and Scheduling

#### Q31. Design root-cause analysis for a 10,000-GPU training cluster.

**Model answer.** Join three graphs: the logical execution graph, the physical network/topology graph, and the software-stack dependency graph. Instrument low-overhead progress at collective boundaries, correlate it with GPU, NVLink, PCIe, NIC, switch, kernel, and storage telemetry, and retain a local high-fidelity ring buffer. Compare equivalent ranks and iterations to find the earliest divergence, then rank endpoint and shared-link causes. Use active probes only when passive evidence is insufficient. Measure top-k culprit accuracy, localization latency, false positives, overhead, MTTR, and GPU-hours saved.

#### Q32. How do you distinguish a root cause from synchronized symptoms?

**Model answer.** In collective training, one failed or slow rank can make every healthy rank wait, so error count and correlation are misleading. I would find the earliest missing progress event, compare peers executing the same operator, and traverse the expected communication dependencies backward. Cross-iteration recurrence and physical-path overlap help separate workload variation from a degraded GPU, NIC, link, or switch. A causal timeline is more useful than the loudest log.

#### Q33. What does a TSDB for AI observability need?

**Model answer.** It needs high-rate WAL-backed ingestion, time and series partitioning, timestamp/value compression, immutable blocks and compaction, a fast recent-data tier, tag indexes with cardinality control, retention and downsampling classes, tenant quotas, and scalable range aggregation. AI telemetry can create a series per rank, operator, collective, and device, so label governance is essential. Capacity includes samples per second, retention, compressed bytes per sample, replication, and WAL/index/compaction headroom.

#### Q34. How would you build a safe automatic TSDB tuner?

**Model answer.** Observe ingestion, cardinality, query mix, cache behavior, resource use, and compaction debt. Restrict actions to influential knobs such as sharding, cache split, block duration, compaction concurrency, query parallelism, retention, and downsampling. Optimize p99, dropped samples, lag, and cost under memory and durability constraints. Evaluate on a canary, apply gradual changes with hysteresis, detect workload drift, and keep an independent health path because the TSDB supplies the tuner's own feedback.

#### Q35. Design a serverless elastic filesystem for AI workloads.

**Model answer.** Use durable object or replicated-SSD data storage, a transactional metadata store, elastic stateless metadata workers, a DRAM/NVMe cache tier, and both compatibility and native high-performance clients. Cache metadata opportunistically but retain one authoritative state. Prewarm predictable training or inference bursts, co-scale metadata QPS, bandwidth, IOPS, and cache, and enforce tenant admission control. Immutable datasets simplify caching; checkpoints use versioned shards and atomic manifest publication.

#### Q36. A training job has low GPU utilization. How do you prove storage is the bottleneck?

**Model answer.** Inspect GPU timelines, input queue occupancy, and per-rank data-wait time. Compare required sample rate with metadata, storage, network, decode, transform, host-to-device, and GPU-consumption rates. Run RAM-backed, cached, no-op-transform, and packed-record experiments. If RAM remains slow, preprocessing or synchronization is likely; if packing files helps, metadata is implicated. One slow rank can stall all workers, so p99 per-rank latency matters more than aggregate bandwidth.

#### Q37. How would you reduce checkpoint overhead without weakening correctness?

**Model answer.** Separate capture from persistence. Copy state quickly into pinned host memory or local NVMe, resume training, and persist asynchronously. Deduplicate replicated tensors, balance writes, compress selectively, and reshard during recovery. Correctness uses immutable versioned shards, checksums, idempotent retries, and one atomic manifest published only after every required shard is durable. Readers never use an uncommitted checkpoint.

#### Q38. What belongs on a DPU, and what should remain on the host?

**Model answer.** Offload frequent bounded-state data-path work such as transport, DMA, checksums, encryption, compression, replication, QoS, and storage protocol processing. Keep complex policy, placement, recovery coordination, and rare operations on the host. Include host-DPU PCIe transfer, DPU compute and memory, and the outgoing path in the cost. Batch requests, pipeline engines, expose observability, retain a host fallback, and evaluate host cores saved, GPU utilization, p99, throughput per watt, and failure behavior.

#### Q39. How would you schedule jobs across heterogeneous CPU, GPU, memory, network, and storage?

**Model answer.** Predict each job's goodput and resource sensitivity by placement, then optimize resource cost, SLO penalty, state movement, and energy under capacity, topology, compatibility, gang, and fairness constraints. Training goodput multiplies throughput by statistical efficiency; inference goodput counts only requests meeting TTFT and TPOT. Profile a bounded set of configurations, update models online, reserve uncertainty headroom, and resize only when remaining benefit exceeds checkpoint, transfer, restart, warmup, and transient SLO cost.

#### Q40. How should rack power be controlled?

**Model answer.** Use a fast local loop for hard cap enforcement and thermal safety, plus a slower global loop for placement, power allocation, and headroom. Exploit per-job performance-power curves because maximum power does not always minimize energy or cost. Protect latency-critical services before best-effort work, include telemetry delay and actuator failure margins, and apply hysteresis to avoid oscillation. Report useful work per joule, SLO-attaining goodput, cap violations, and performance impact.

#### Q41. What is the right metric for an elastic training scheduler?

**Model answer.** Raw throughput is insufficient because changing batch size or parallelism changes statistical efficiency and convergence. Goodput captures useful progress per time. The scheduler should also track finish-time fairness, queueing, checkpoint and reconfiguration overhead, failures, and cost. An optimization that raises instantaneous samples per second but delays convergence or repeatedly migrates state is not a win.

### F. Research Method and Behavioral Questions

#### Q42. Tell me about a failed idea.

**Model answer.** Choose a real example where the hypothesis was plausible but a controlled measurement disproved it. Explain the initial model, the counterexample, the profile or experiment that isolated the cause, and the design change. A strong pattern is: the filter reduced rows but increased latency because probe CPU or cache pressure became dominant; you then added a budget, delayed activation, or a no-filter fallback. The point is evidence-driven revision, not a disguised success story.

#### Q43. How do you establish that a performance improvement is causal?

**Model answer.** State a mechanism, predict which counters should change, and run a controlled ablation that changes only that mechanism. Use repeated trials, distributions and confidence intervals, fixed input and system conditions, and warm versus cold distinctions. Cross-check operator counters with end-to-end results and test a workload where the mechanism predicts no benefit. A speedup without corresponding resource evidence may be noise or an unrelated plan change.

#### Q44. How do you balance a research prototype with production quality?

**Model answer.** Keep the research question narrow but make its boundary explicit. I first build the smallest end-to-end path that tests the hypothesis, then add correctness invariants, diagnostics, deterministic benchmarks, fallback behavior, and integration tests in proportion to risk. I separate experimental knobs from stable interfaces and document unsupported cases. Productionization is not polishing every component; it is making failure, ownership, and evidence visible.

#### Q45. What would you do in your first 90 days?

**Model answer.** In days 1-30, learn the workload, code paths, success metrics, and current bottlenecks; reproduce one benchmark and one incident or regression. In days 31-60, select a narrow hypothesis near my strength, such as candidate reduction before a semantic operator or adaptive filtered ANN, and build a measurable prototype. In days 61-90, validate quality and resource tradeoffs, document negative cases, integrate guardrails, and propose a longer research agenda based on production evidence.

#### Q46. Why this role?

**Model answer.** It joins my core interest in query optimization with the resource and correctness challenges introduced by AI operators. The attractive research problem is not simply adding an LLM function to SQL; it is designing one system that reasons about exact relational semantics, approximate retrieval, stochastic inference, CPU/GPU/storage placement, and verified operational control. I can contribute immediately on query reduction and runtime adaptation while deliberately growing into vector infrastructure and AI-cluster systems.

#### Q47. What are thoughtful questions to ask the interviewer?

**Model answer.** Ask which research direction is attached to this opening; what production workload or metric currently limits it; how the team balances publishable research with platform delivery; what artifacts a new researcher is expected to own; how quality is evaluated for semantic or agentic operators; and which decisions are centralized versus owned by storage, scheduler, database, and model teams. Avoid questions whose answer is already in the JD.

---

## 13. System Design Answer Frameworks

### 13.1 Unified Multimodal Query Engine

**Prompt.** Design a system that supports relational SQL, full-text search, vector retrieval, image/document analysis, and LLM predicates.

**Clarify first:** data scale and update rate; latency and cost SLO; exact versus approximate semantics; required recall and quality; model locality; tenant isolation; supported joins and transactions.

**Logical layer:** define scalar, lexical, vector, semantic filter/join/top-k/aggregate, and tool operators. Attach determinism, error contract, side effects, model/index version, and required context.

**Optimizer:** enumerate exact pushdown, candidate generators, fusion order, model cascade, batching, caching, factorization, and CPU/GPU placement. Optimize latency, money, energy, and resources under quality constraints, using samples and runtime feedback.

**Execution:** preserve row IDs, run sparse/dense retrieval, adapt oversampling, delay wide payload reads, batch inference, apply backpressure, validate exact predicates, and emit provenance.

**Reliability:** version models, embeddings, prompts, and indexes; bound retries; isolate tenants; protect rate limits; support deterministic replay where possible.

**Evaluation:** SQL correctness, recall@k/nDCG, semantic quality, p50/p99, QPS, model calls, tokens, GPU seconds, bytes read, peak memory, cost, and update visibility.

### 13.2 Cloud-Native Filtered Vector Service

**Prompt.** Design a multi-tenant service for billions of vectors with metadata filters and online updates.

**Data plane:** route through centroids or partition metadata; search immutable per-segment indexes plus a mutable delta; use HNSW, IVF/PQ, or SSD graph according to memory and update constraints; rerank exact vectors and merge global top-k.

**Filtering:** select pre-, post-, or in-index filtering from selectivity and neighborhood correlation. Maintain eligibility bitmaps or workload-specific subindexes where useful. Adapt oversampling and expose an exact fallback.

**Cloud control plane:** versioned manifests, snapshot publication, compaction, re-embedding, shard placement, replicas, rebalancing, quota, admission control, and tenant-aware cache.

**Tail control:** selective routing, asynchronous reads, queue isolation, slow-shard detection, calibrated local recall budgets, and cautious hedging.

**Failure tests:** lost shard, stale replica, partial manifest publication, embedding-version mismatch, hot tenant, skew, update storm, and remote-storage slowdown.

### 13.3 AI-Cluster Observability and RCA

**Prompt.** Diagnose hangs and slowdowns across 10,000 GPUs.

**Signals:** collective progress, iteration phase, GPU kernels, utilization, clocks, errors, NVLink, PCIe, NIC, switch, CPU, memory, storage, logs, traces, and profiles. Keep continuous low-cost telemetry and a local high-fidelity ring buffer.

**Representation:** join logical execution, physical topology, and software dependency graphs. Normalize peer ranks and iterations before anomaly detection.

**Diagnosis:** detect divergence, localize the first stalled dependency, rank endpoint/link/shared-component hypotheses, explain evidence, and trigger a targeted active test when uncertainty is high.

**Action:** recommend first; automatically drain, retry, reroute, or quarantine only under confidence and blast-radius gates. Verify recovery and roll back.

**Evaluation:** injected and historical faults, unseen topologies, top-k root cause, calibration, time to detect/localize/recover, overhead, false intervention, and GPU-hours saved.

### 13.4 Serverless AI Storage with DPU Acceleration

**Prompt.** Build elastic storage for training data, model loading, checkpoints, and inference state.

**Separate workloads:** small-file shuffled reads, burst checkpoints, model fan-out, and latency-sensitive KV/state access require different paths.

**Architecture:** durable object/SSD tier, transactional metadata, elastic metadata workers, DRAM/local-NVMe cache, workload-aware prefetch, native asynchronous/RDMA client plus compatibility path, and tenant admission control.

**Checkpoint protocol:** short capture to host/NVMe, asynchronous persistence, immutable shards, checksums, idempotent retry, atomic manifest, parallelism-agnostic resharding.

**DPU split:** offload bounded data-plane transport, DMA, checksum, encryption, compression, replication, and QoS; keep policy and recovery on the host. Compare full path time and retain fallback.

**Evaluation:** GPU data-wait, metadata p99, throughput, bytes copied, host cores, cache hit rate, checkpoint pause/persist/recovery, cost, power, fairness, and failure semantics.

### 13.5 Guarded Infrastructure Agent

**Prompt.** Build an agent that diagnoses incidents and tunes production systems.

**Tools and evidence:** expose typed read tools for metrics, logs, traces, topology, config, deployment history, and runbooks. Every observation has a source, timestamp, and environment version.

**Planning:** let the LLM form hypotheses and propose a typed plan. Use deterministic validation for authorization, invariants, compatibility, budgets, and rollback; use a constrained optimizer for feasible allocation.

**Actuation ladder:** read-only -> replay -> shadow -> canary -> bounded rollout -> promotion. Require human approval for high-impact actions and preserve an independent kill switch.

**Memory and skills:** immutable evidence, versioned candidate skills, provenance, tests, least privilege, expiry, signing, revocation, and no in-place production mutation.

**Adversarial evaluation:** missing or poisoned telemetry, prompt injection in logs, stale runbooks, conflicting signals, partial tool failure, delayed metrics, rollback failure, and compromised credentials.

---

## 14. Prioritized Reading and Study Plan

All entries below are primary papers, proceedings pages, or official technical documentation. Read for the problem, invariant, architecture, cost model, evaluation method, and failure boundary - not merely the headline result.

### 14.1 P0: Read and Explain Without Notes

1. [Yannakakis, Algorithms for Acyclic Database Schemes, VLDB 1981](https://www.sigmod.org/publications/dblp/db/conf/vldb/Yannakakis81.html) - foundation for the candidate's research identity.
2. [Predicate Transfer, CIDR 2024](https://www.vldb.org/cidrdb/papers/2024/p22-yang.pdf) - modern filter propagation across join graphs.
3. [LOTUS, PVLDB 2025](https://www.vldb.org/pvldb/vol18/p4171-patel.pdf) - semantic operators and quality-aware optimization.
4. [Palimpzest, CIDR 2025](https://www.vldb.org/cidrdb/2025/palimpzest-optimizing-ai-powered-analytics-with-declarative-query-processing.html) - plan search over models, prompts, cost, and quality.
5. [SingleStore-V, PVLDB 2024](https://www.vldb.org/pvldb/vol17/p3772-chen.pdf) - integrated SQL, vector, full-text, filters, and distributed execution.
6. [SIEVE, PVLDB 2025](https://www.vldb.org/pvldb/vol18/p4723-li.pdf) - filtered vector search and workload-specific index collections.
7. [VBase, OSDI 2023](https://www.usenix.org/conference/osdi23/presentation/zhang-qianxi) - incremental vector candidate generation inside a relational engine.
8. [Spider 2.0, ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/46c10f6c8ea5aa6f267bcdabcb123f97-Abstract-Conference.html) - realistic enterprise Text-to-SQL workflows.
9. [MegaScale, NSDI 2024](https://www.usenix.org/conference/nsdi24/presentation/jiang-ziheng) - production LLM training at more than 10,000 GPUs.
10. [ByteCheckpoint, NSDI 2025](https://www.usenix.org/conference/nsdi25/presentation/wan-borui) - unified checkpointing and resharding for foundation-model development.
11. [Synergy, OSDI 2022](https://www.usenix.org/conference/osdi22/presentation/mohan) - CPU/GPU/memory-aware scheduling.
12. [Bao](https://arxiv.org/abs/2004.03814) and [Eraser, PVLDB 2024](https://www.vldb.org/pvldb/vol17/p926-zhu.pdf) - bounded learning and regression safety for query optimization.

For each P0 paper, prepare a six-line card:

- problem and workload;
- key insight;
- system design;
- optimization objective or invariant;
- strongest evaluation result in your own words;
- one limitation and one connection to your work.

### 14.2 P1: Build Breadth and Comparisons

**Query and semantic systems**

- [Free Join](https://arxiv.org/abs/2301.10841)
- [Beyond Quacking / FlockMTL, PVLDB 2025](https://www.vldb.org/pvldb/vol18/p5415-mhedhbi.pdf)
- [InferF, SIGMOD 2026 preprint](https://arxiv.org/abs/2511.20489)
- [CAESURA, CIDR 2024](https://vldb.org/cidrdb/2024/caesura-language-models-as-multi-modal-query-planners.html)

**Vector systems**

- [DiskANN, NeurIPS 2019](https://proceedings.neurips.cc/paper_files/paper/2019/hash/09853c7fb1d3f8ee67a61b6bf4a7f8e6-Abstract.html)
- [SPANN, NeurIPS 2021](https://proceedings.neurips.cc/paper_files/paper/2021/hash/299dc35e747eb77177d9cea10a802da2-Abstract.html)
- [SPFresh](https://www.microsoft.com/en-us/research/publication/spfresh-incremental-in-place-update-for-billion-scale-vector-search/)
- [DistVS, NSDI 2026](https://www.usenix.org/system/files/nsdi26-yin.pdf)

**Text-to-SQL and agents**

- [Spider, EMNLP 2018](https://aclanthology.org/D18-1425/)
- [BIRD, NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/83fc8fab1710363050bbd1d4b8cc0021-Abstract-Datasets_and_Benchmarks.html)
- [PICARD, EMNLP 2021](https://aclanthology.org/2021.emnlp-main.779/)
- [OmniSQL, PVLDB 2025](https://www.vldb.org/pvldb/vol18/p4695-li.pdf)
- [InfiAgent-DABench, ICML 2024](https://proceedings.mlr.press/v235/hu24s.html)

**Observability and storage**

- [Holmes, NSDI 2025](https://www.usenix.org/conference/nsdi25/presentation/yao)
- [Aegis, NSDI 2025](https://www.usenix.org/conference/nsdi25/presentation/dong)
- [Gorilla, PVLDB 2015](https://www.vldb.org/pvldb/vol8/p1816-teller.pdf)
- [Monarch, PVLDB 2020](https://research.google/pubs/monarch-googles-planet-scale-in-memory-time-series-database/)
- [Pocket, OSDI 2018](https://www.usenix.org/conference/osdi18/presentation/klimovic)
- [ServerlessLLM, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/fu)
- [Characterizing Off-path SmartNIC, OSDI 2023](https://www.usenix.org/system/files/osdi23-wei-smartnic.pdf)

**Scheduling and agent safety**

- [Dominant Resource Fairness, NSDI 2011](https://www.usenix.org/conference/nsdi11/dominant-resource-fairness-fair-allocation-multiple-resource-types)
- [Pollux, OSDI 2021](https://www.usenix.org/conference/osdi21/presentation/qiao)
- [Zeus, NSDI 2023](https://www.usenix.org/conference/nsdi23/presentation/you)
- [Llumnix, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/sun-biao)
- [AIOpsLab, MLSys 2025](https://proceedings.mlsys.org/paper_files/paper/2025/hash/d1f9e4a9f109b6e8b75ed362736f22ec-Abstract-Conference.html)
- [ToolEmu, ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/hash/7274ed909a312d4d869cc328ad1c5f04-Abstract-Conference.html)

### 14.3 P2: Frontier and Optional Depth

- [I Cannot Believe It Is Not Yannakakis, CIDR 2026](https://www.vldb.org/cidrdb/2026/i-cant-believe-its-not-yannakakis-pragmatic-bitmap-filters-in-microsoft-sql-server.html)
- [KathDB, CIDR 2026](https://www.vldb.org/cidrdb/papers/2026/p14-xiao.pdf)
- [FlowANN, OSDI 2026](https://www.usenix.org/conference/osdi26/presentation/zhao)
- [FLARE, NSDI 2026](https://www.usenix.org/conference/nsdi26/presentation/cui)
- [EROICA, NSDI 2026](https://www.usenix.org/conference/nsdi26/presentation/guan-yu)
- [SDCHunter, OSDI 2026](https://www.usenix.org/conference/osdi26/presentation/zheng)
- [MUSE-Autoskill, 2026 preprint](https://arxiv.org/abs/2605.27366)

Treat preprints and future-conference papers as frontier signals. Verify their final status before an interview and avoid presenting preliminary claims as settled production evidence.

### 14.4 Four-Week Preparation Schedule

| Week | Reading and concepts | Hands-on output | Interview output |
|---|---|---|---|
| 1 | Yannakakis, Predicate Transfer, LOTUS, Palimpzest | Annotate one semantic query plan and its cost/quality alternatives | Research introduction; Q1-Q17 |
| 2 | SingleStore-V, SIEVE, VBase, DiskANN/SPANN | Prototype or simulate filtered ANN strategies across selectivity and correlation | Q18-Q24; vector design |
| 3 | Spider 2.0, PICARD, MegaScale, Holmes, ByteCheckpoint | Draw Text-to-SQL verification and 10,000-GPU RCA architectures | Q25-Q38; RCA/storage designs |
| 4 | Synergy, Pollux, Zeus, Bao/Eraser, AIOpsLab | Write one guarded-agent spec and rehearse all system designs | Q39-Q47; two mock interviews |

Daily cadence:

1. 60-90 minutes of primary-source reading.
2. 30 minutes writing paper cards and cross-paper comparisons.
3. 45 minutes implementing, profiling, or designing one concrete mechanism.
4. 30 minutes answering two questions aloud and reviewing the recording.

### 14.5 Practical Mini-Projects

Choose one deep project rather than many superficial demos.

**Option 1: Filtered ANN optimizer.** Implement pre-filter, post-filter, and adaptive selection over an ANN library plus exact metadata bitmaps. Generate datasets with controlled selectivity and filter-vector correlation. Measure recall, p99, distance computations, bytes read, and memory.

**Option 2: Semantic join reducer.** Add an embedding proxy and expensive verifier to a multiway join pipeline. Compare join-then-infer, exact semijoin reduction, proxy candidate generation, distinct-value caching, and factorized inference.

**Option 3: Verified Text-to-SQL harness.** Combine schema retrieval, constrained generation, parse/bind validation, bounded execution, result invariants, and provenance. Evaluate on schema changes and ambiguous business terms, not only benchmark accuracy.

Each project should include reproducible scripts, a correctness oracle, an architecture diagram, resource counters, negative cases, and a short design document.

---

## 15. Final Interview Checklist

### 15.1 Technical Readiness

- Explain Yannakakis, semijoins, runtime filters, Bloom sizing, and outer-join caveats precisely.
- Compare exact, approximate, and stochastic operators by their error contracts.
- Design a multimodal plan across SQL, BM25, vector, and LLM/VLM execution.
- Explain filtered ANN under selectivity and neighborhood correlation.
- Compare HNSW, IVF/PQ, SSD indexes, immutable segments, and mutable deltas.
- Design enterprise Text-to-SQL with authorization, grounding, sandboxing, and verification.
- Diagnose AI-cluster faults using logical, physical, and software graphs.
- Distinguish storage bandwidth, metadata, preprocessing, network, and straggler bottlenecks.
- Explain checkpoint atomicity, state movement, and DPU offload boundaries.
- Formulate heterogeneous scheduling using goodput, SLOs, fairness, state cost, and power.
- Describe a guarded agent loop with typed tools, deterministic validation, canary, and rollback.

### 15.2 Evidence Readiness

- Know your precise contribution to every project and paper.
- Carry real dataset scale, baselines, hardware, and measured results.
- Show a plan or profile that demonstrates the mechanism.
- Prepare one correctness challenge, one regression, and one failed hypothesis.
- Separate CPU, memory, I/O, network, and accelerator evidence.
- State limitations before the interviewer has to discover them.
- Verify the current publication status of 2026 papers and preprints.

### 15.3 Communication Readiness

- Start with semantics and SLOs, then architecture, cost, adaptation, and evaluation.
- Use one clear research identity rather than claiming equal depth across the JD.
- Tie unfamiliar areas to transferable principles without overstating implementation experience.
- Quantify only what you measured.
- Answer the question first; add details on request.
- End design answers with failure handling, metrics, and decisive experiments.

### 15.4 Final 30-Second Pitch

> I specialize in making query systems avoid unnecessary work. My background in Yannakakis-style evaluation, join optimization, and runtime filters taught me to connect semantics with CPU, memory, and I/O behavior. I want to carry that approach into AI-native infrastructure: reduce candidates before expensive semantic inference, optimize hybrid SQL and vector plans under explicit quality constraints, and use runtime evidence to adapt execution safely. This role is a strong fit because it connects that database foundation to distributed retrieval, heterogeneous systems, and verified AI agents.

### 15.5 Final Principle

The unifying idea across this broad role is:

> Move less data, invoke expensive intelligence on fewer and better candidates, allocate heterogeneous resources according to useful progress, and never let an adaptive system act without measurable quality, safety, and rollback boundaries.
