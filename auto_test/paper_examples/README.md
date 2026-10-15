# Standalone mechanism queries

`tpch/` contains benchmark SELECT statements. `diagnostics/` contains standalone
correctness and candidate-query inputs recovered from historical output bundles.
These are separate from the main 321-query workload.

```bash
python3 auto_test/paper_examples/run_example.py \
  --db tpch_1.duckdb --query auto_test/paper_examples/tpch/customer_orders_lineitem.sql \
  --threads 4 --runs 5
```

Use `--help` on the individual runners for forced-order, statistics, and thread
sweep experiments. Run release builds and execute bare SELECTs for correctness.
All runners' output directories belong under `auto_test/results/` or outside
the repository. Plans, timing observations, environment captures, figures, and
paper narratives are ignored artifacts; this directory publishes no recorded
performance results. Do not infer timings from the presence of a query.
