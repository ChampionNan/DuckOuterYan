# PostgreSQL plan comparison tools

This directory retains comparison code, query inputs, configuration, and the
PostgreSQL instrumentation patch. It contains no distributed execution results.

- `queries/` and `cases.json`: the retained comparison inputs.
- `patches/`: PostgreSQL outer-join tracing instrumentation.
- `server.sh` / `server.py`: build, load, and run the comparison on a local server.
- `benchmark_examples.sh`: run the fixed benchmark cases listed in
  `benchmark_examples.txt` using explicitly supplied databases and PostgreSQL paths.
- `fair_baseline.py`, the C/C++ runners, and measurement scripts: bare-query
  correctness, plan inspection, and timing.
- `package.py`: Linux source packaging; consult `--help` for its explicit inputs.

```bash
python3 auto_test/pg_plan_comparison/server.py --help
python3 auto_test/pg_plan_comparison/run.py --help
```

The server entry point defaults to `auto_test/results/pg-plan-comparison-work`.
Place every custom work/result directory under ignored `auto_test/results/` or
outside the repository. PostgreSQL data directories, exported tables, EXPLAIN
plans, traces, captures, timing CSVs, and generated paper fragments are outputs.
Historical comparison reports and server-specific launch instructions are not
part of the anonymous artifact.

Use the current release engine and matched shared library for measurements.
Correctness comparisons require bare queries and complete result multisets.
Plan-replay experiments must report their baseline and timing method explicitly;
a captured plan alone is not a measured runtime result.
