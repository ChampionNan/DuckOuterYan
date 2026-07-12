# DuckYanOuter Codex Guide

This repository is a DuckDB research fork focused on query optimization and
execution, especially OuterYan join reordering, two-round semi-join reduction,
aggregate pushdown, and bitmap/hash filter kernels.

## Engineering conventions

- Write production-grade, readable C++ with concise comments. Prefer RAII,
  DuckDB's existing abstractions, and zero-overhead designs.
- Inspect concrete DuckDB symbols and call sites before changing optimizer or
  pipeline behavior. Do not invent paths or APIs.
- Preserve scalar fallbacks for SIMD work and isolate SIMD in leaf functions.
- Respect `DataChunk` vectorization and avoid per-tuple allocation.
- Keep build/probe pipeline dependencies explicit through `MetaPipeline`; a
  probe must not run before its build has finalized.
- Treat logical/physical operator enum additions as serialization-compatibility
  changes.
- Include paths must remain case-correct for Linux.

## Relevant areas

- `src/optimizer/outer_yan/` and
  `src/include/duckdb/optimizer/outer_yan/` — OuterYan IR and passes.
- `src/optimizer/join_order/` — DuckDB DPhyp and cost-model patterns.
- `src/execution/operator/join/physical_sj_{build,probe}.cpp` — semi-join
  runtime operators and filter kernels.
- `auto_test/experiment_onoff.sh` — bare-query ON/OFF correctness and
  performance harness.
- `test/optimizer/outer_yan/` and `test/sql/optimizer/outer_yan/` — focused
  C++ and SQL coverage.

## OuterYan invariants

- Correctness comparisons must execute the bare query. Wrapping it in
  `CREATE TABLE AS`, `COPY`, or adding `LIMIT` can produce a different plan and
  mask optimizer defects.
- OFF means `SET disabled_optimizers TO 'outer_yan';`; ON means the empty
  disabled-optimizer list.
- Join kind is children-relative. If DP swaps operands, LEFT and RIGHT must be
  flipped while INNER and FULL remain unchanged.
- The bottom-up semi-join round must finish before the top-down round. Never
  coalesce operators across this phase boundary.
- Compare join groupings against DuckDB's normally optimized candidate using
  stable base-table identities; ignore join kind, child orientation, and SJ
  wrappers. A same-grouping result always uses the DuckDB candidate.
- `OuterYanOptimizer::APPLY_COST_GATE` defaults to true. When enabled, select
  OuterYan only if real-join cost plus `SEMIJOIN_COST_RATIO` times fixed SJ work
  is within `MAX_CANDIDATE_TO_BASELINE_RATIO` of the baseline; all are
  source-level experiment knobs, not session variables.
- Bitmap budget is per filter. `outer_yan_bitmap_max_bytes=0` remains the hash
  fallback escape hatch.

## Validation

- Use a release build for performance conclusions; debug timings are only
  directional.
- Focused build: `GEN=ninja make debug` or the repository's existing Ninja
  target when a build directory already exists.
- Focused tests include `build/debug/test/unittest "[outer_yan]"` and
  `test/sql/optimizer/outer_yan/bitmap_budget.test`.
- For corpus validation, start small with
  `auto_test/experiment_onoff.sh --only graph --limit N`, then widen only after
  correctness and plan-shape checks pass.
- Useful diagnostics: `PRAGMA enable_verification`,
  `PRAGMA verify_parallelism`, `PRAGMA explain_output='all'`,
  `DUCKDB_OYTRACE`, and `DUCKDB_SJ_KERNEL_TRACE`.

Do not commit, create branches, open PRs, auto-format unrelated code, or run a
full expensive corpus unless the user asks.
