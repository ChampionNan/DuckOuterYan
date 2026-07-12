# OuterYan Figures

These figures are produced by [`auto_test/plot_speedup.py`](../../plot_speedup.py) from the
`experiment_onoff_*.csv` result files. 

### The one rule that explains every figure
**speed-up = time(OFF) / time(ON).**
- **> 1** → OuterYan **ON is faster** (good).
- **= 1** → no difference.
- **< 1** → OuterYan **ON is slower** (regression).

A dashed/grey line at **1.0** appears on every chart as the break-even reference.
`T1` = single-thread, `TM` = multi-thread. Only **correct & timed** queries are
plotted; `TIMEOUT`/`ERROR` rows are dropped (the skipped count is printed to stdout).

---

## Folder layout

```
plots/
├── <run>/                 # one sub-folder per source CSV (e.g. 20260622_081932/)
│   ├── speedup_by_kernel_joinorder.pdf  speedup_by_benchmark.pdf  speedup_by_shape.pdf
│   ├── speedup_by_relations.pdf
│   └── per_query_graph.pdf  per_query_tpch.pdf  per_query_tpcds.pdf  per_query_job.pdf
└── machine_cmp.pdf        # only when ≥2 CSVs: run-vs-run comparison
```
A family figure (e.g. `per_query_job.png`) **only exists if that run actually has
timed queries in that family** — a run with no JOB results produces no JOB figure.

---

## Vocabulary used by the figures

| term | meaning |
|---|---|
| **kernel** | which semi-join filter ran: **bitmap** (cheap, integer keys) · **mixed** (≥1 expensive hash filter) · **none** = `b0h0` (no filter inserted → ON ≈ OFF) |
| **reorder** | `Yes` = OuterYan changed the join order; `No` = filters applied but order unchanged |
| **family** | `graph` (synthetic chains) · `TPC-H` · `TPC-DS` · `JOB` |
| **topology** | join-graph shape: `line` · `bushy` · `bushyBal` · `rdeep` · `branch` · `star` · `agg` · `real` |
| **T1 / TM** | single-thread / multi-thread speed-up |

---

## Topology & query-name glossary

A query name encodes its shape and data, e.g. `rdeep_N4_mixB_s01` or
`oy_th_th_bushy4a_v3`. The **topology** is the shape of the join tree (how the
relations are nested). `⋈` below is a join node; `R1..Rn` are the base tables.

**`line`** — *left-deep chain.* Each table joins onto the running result; the
classic `R1→R2→R3→R4` pipeline. The build side keeps growing on the left.
```
        ⋈            (((R1 ⋈ R2) ⋈ R3) ⋈ R4)
       / \
      ⋈   R4
     / \
    ⋈   R3
   / \
  R1  R2
```

**`rdeep`** — *right-deep chain.* Same chain, nested the other way: one table
probes into a deep stack of pre-built joins. This is the shape predicate-transfer
+ reorder helps most (a tiny driver can prune the whole stack).
```
  ⋈                 (R1 ⋈ (R2 ⋈ (R3 ⋈ R4)))
 / \
R1  ⋈
   / \
  R2  ⋈
     / \
    R3  R4
```

**`bushy`** — *unbalanced bushy tree.* Independent sub-trees are joined together
rather than one long chain; one side is deeper than the other.
```
       ⋈           ((R1 ⋈ R2) ⋈ ((R3 ⋈ R4) ⋈ R5))
      /  \
     ⋈    ⋈
    / \   / \
   R1 R2 ⋈  R5
         /\
        R3 R4
```

**`bushyBal`** — *balanced bushy tree.* Two roughly equal halves joined at the
top — the most parallel-friendly shape.
```
          ⋈        (((R1 ⋈ R2) ⋈ R3) ⋈ ((R4 ⋈ R5) ⋈ R6))
        /    \
      ⋈        ⋈
     / \      / \
    ⋈   R3   ⋈   R6
   / \      / \
  R1 R2    R4 R5
```

**`star`** — *star schema.* One central fact table; every other relation joins
directly to it (no chain). TPC-H/TPC-DS/JOB only — not in the graph corpus.
```
        fact          fact ⋈ D1, ⋈ D2, ⋈ D3, ⋈ D4
      / |  | \         (all dimensions key off the center)
    D1 D2 D3 D4
```

**`branch`** — *Y-shaped tree.* Two separate sub-chains that merge at a shared
relation (a fork), e.g. two dimension paths meeting at a fact.
```
   R1-R2-R3   R4-R5      two chains feeding…
        \      /
         ⋈----⋈          …a common join node
```

**`agg`** — **not a shape**: an *aggregation query* (`COUNT/SUM/MIN/MAX`, no AVG,
with `GROUP BY`) layered on top of a join tree. These tend to **regress** (tiny
output, serial filter-build tax) — see `ratio.png`.

**`real`** — **not a shape**: hand-written *realistic* business queries on the
real schema (e.g. `oy_th_real_custdist`, `oy_ds_real_store_dims`), as opposed to
the systematically generated topologies above.

### Other name tokens
| token | meaning |
|---|---|
| `N3 … N6` | number of joined relations (chain depth) |
| `mixA / mixB / mixC` | cyclic pattern of join *types* along the tree — `mixA = LEFT,INNER,RIGHT,FULL`; `mixB = FULL,RIGHT,INNER,LEFT`; `mixC = RIGHT,FULL,LEFT,INNER` |
| `s01 … s95` | selectivity of the `WHERE R1.src % k` predicate ≈ % of base rows kept → result size (`s01`≈1%, `s95`≈95%); the `rows` column grows with it |
| `_rd_` | right-deep variant of a chain topology (chains only) |
| `_v0 … _v5` | variant index — same topology, a different join-type mix |
| `oy_th_ / oy_ds_ / oy_jb_` | family prefix: TPC-H (sf100) / TPC-DS (sf100) / JOB(IMDb) |

---

## Figure-by-figure

### `speedup_by_kernel_joinorder.pdf` — distribution by kernel & by join order (one figure, two panels)
- **Left** (*Speed-up by kernel*) groups by **bitmap / mixed / none**; **right** (*Speed-up by join order*) by **reorder = Yes / No**. Each group has two boxes: **blue = T1**, **orange = TM**, with raw points jittered over them; log y-axis; `n=` under each group.
- **How to read:** box = inter-quartile range, black line = median, dots = individual queries; the **white diamond + small number** beside each box is the **geometric mean**.
- **Takeaway:** **bitmap** spans a huge positive range (up to ~90×); **mixed** sits mostly **below 1** (regresses, worse on TM); **none** hugs 1.0. `reorder=Yes` carries the big wins but also the blow-ups; `reorder=No` is tighter and still positive on chains.

### `speedup_by_benchmark.pdf` — speed-up by benchmark family
Same box format, grouped by **graph / TPC-H / TPC-DS / JOB**; diamond + number = geomean.
- **Takeaway:** **graph** chains win big (TM geomean ~2×), **JOB** ~1.2×, **TPC-H/TPC-DS** mixed-to-negative.

### `speedup_by_shape.pdf` — speed-up by join-graph **shape** (a query variable)
Same box format, grouped by topology (`line, bushy, bushyBal, rdeep, rd, branch, agg, real`); x-labels horizontal, geomean number placed **above** each box.
- **Takeaway:** `line`/`rdeep`/`bushyBal` lean positive; `agg` carries most regressions.

### `speedup_by_relations.pdf` — speed-up by chain depth (#relations), graph corpus
Single box panel grouped by **#relations** (`N3, N4, …`); geomean number above each box. Graph corpus only (where depth varies systematically).
- **Takeaway:** deeper chains win more — N4 TM geomean ~3.1× vs N3 ~1.7× (more relations = more predicate-transfer reduction).

### `per_query_graph.pdf` · `per_query_tpch.pdf` · `per_query_tpcds.pdf` · `per_query_job.pdf`
- **Every timed query in that family**, one horizontal row, sorted by speed-up. Each row has an **orange bar = TM** and a **grey bar = T1** beneath it — one consistent colour (kernel is **not** colour-coded); log x; reference line at 1.
- **Bar thickness is fixed**, so the figure height grows with the query count — it adapts to any corpus size without crowding. Exact values are labelled only when a family has ≤ 24 rows (else too dense).
- **How to read:** scan top→bottom; where the orange (TM) bar is shorter than the grey (T1) bar, multi-thread helped less than single-thread.
- **Takeaway:** the full per-query detail for one family.

### `machine_cmp.png` — run-vs-run (root folder, only with ≥2 CSVs)
- **x = TM speed-up on run A, y = TM speed-up on run B**, one dot per query common to both; log-log with the y=x diagonal.
- **How to read:** dots on the diagonal = the two runs/machines agree; off-diagonal = a query that behaved differently between runs.
- **Takeaway:** confirms results are consistent across machines (points hug the diagonal) and flags any per-query divergence.

---

## Cheat-sheet — "which figure answers my question?"

| question | look at |
|---|---|
| Does OuterYan help overall, and where? | `speedup_by_benchmark.pdf` |
| Which kernel wins / regresses? | `speedup_by_kernel_joinorder.pdf` (left) |
| Does join order matter? | `speedup_by_kernel_joinorder.pdf` (right) |
| Which exact queries are best/worst? | `per_query_<family>.pdf` |
| Are the two machines consistent? | `machine_cmp.pdf` |
