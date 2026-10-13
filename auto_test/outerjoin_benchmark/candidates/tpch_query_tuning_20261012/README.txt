TPC-H SQL-only tuning proposal, 2026-10-12

Subsequent adoption (2026-10-13)
  The active benchmark now uses exactly 20 of these 31 definitions: all 14
  predicate-only candidates and both complete Q5 groups (bushy/right-deep).
  sources/tpch_tuning_promotion_20261013.json freezes this reviewed choice and
  discloses its post-hoc selection. The remaining 11 definitions stay candidates.
  This directory and the full-pilot tool preserve the historical 31-candidate
  experiment; the original proposal/status text below refers to 2026-10-12.
  Default --all uses the active 20-replacement setting, not the full pilot.

Scope
  31 one-for-one replacement candidates for the 31 TPC-H instances with
  measured speed-up below 1 in CPU9 run 20261010_150834_t32.
  14 change the date predicate only; 17 also change the mixed join pattern.
  Source relations/equality edges, projection, grouping, relation count,
  query class, and supplied tree shape are retained for every slot.
  No optimizer/executor/cost-model changes are part of this proposal.

Status and counts
  This folder is NOT the active benchmark and default --all does not run it.
  The active benchmark still has 720 SQL queries, including 176 TPC-H queries.
  The reference measured selected cohort is 281 overall / 80 TPC-H.
  Of those 80 TPC-H slots, 49 keep their original SQL and 31 have candidates.
  proposed_full_manifest.csv is the proposed 720-slot replacement matrix,
  NOT evidence that the new SQL already has 281/80 valid measurements.
  All other families and raw CPU9 result files remain unchanged.

Selectivity
  The existing bands remain low (0,5%), medium [5,40%), high [40,60%].
  Candidate base-table fractions are approximately 2%, 10%, and 42%.
  One high candidate uses 44% to avoid duplicating another proposed query.
  Candidate counts by band remain low=6, medium=9, high=16.
  These are dated input cohorts, not joined-output selectivity estimates.
  SF1 calibration is recorded in manifest.csv; confirm the bands again on SF50.
  Date windows and some preservation semantics change: these are new workload
  instances, not equivalent rewrites of the old SQL.

Review files
  replacement_map.csv: old/new IDs, pattern changes, fractions, old ratios.
  manifest.csv: only the 31 new SQL candidates, each pending CPU9 measurement.
  proposed_full_manifest.csv: 720-slot count-preserving proposal.
  local_explain_decisions.csv: local selection diagnostics, NOT CPU9 results.
  queries.txt: new candidates, relative to this candidate corpus.
  baseline_queries.txt: original targets, relative to the ACTIVE corpus.
  local_pilot_comparison.csv: every local original/candidate outcome, including
  regressions. These are NOT replacement CPU9 measurements.
  The pinned policy in sources/tpch_query_tuning_20261012.json records the
  reference manifest/result hashes and explicit performance-based selection.

Local validation completed
  Release build, SF1, 4 threads; 31/31 candidates select OuterYan, 31/31 pass
  bare-query OFF/ON multiset equality, and all finish within the local 30-second
  statement limit. Equality was checked separately from the median comparison.
  Old and candidate SQL each use five unprofiled post-warmup runs (no profile).
  Across these 31 target slots, geomean speed-up changes 0.7341x -> 1.0001x;
  21 candidate ratios increase, 10 decrease. Counts at or above 1x change 5 -> 11.
  These small-scale screening results do not establish improvement at SF50 and
  do not establish that every slow query has been fixed. No sampling uncertainty
  is inferred from the stored medians. No candidate is promoted automatically.
  SF1 ratio examples (old -> candidate): Q-H-B-12 0.5992x -> 3.3940x,
  A-H-RD-04 0.7137x -> 3.6865x, Q-H-RD-15 0.6601x -> 1.2073x.
  Counterexample: G-H-LD-03 changes 0.9921x -> 0.3758x; do not hide it.
  Raw local results (under auto_test/results):
    tpch_query_tuning_20261012_sf1.csv                 [equality + one smoke run]
    tpch_query_tuning_20261012_sf1_baseline_median5.csv [original SQL]
    tpch_query_tuning_20261012_sf1_candidate_median5.csv[candidate SQL]
  Smoke-run IDs predate a filename cleanup. All 31 content SHA-256 values match
  the final candidate SQL, and that match was checked before reusing correctness
  evidence. Raw files and the initial input snapshot have not been rewritten.

Reproduce generation without overwriting this review snapshot
  python3 auto_test/prepare_tpch_tuning.py --db tpch_1.duckdb --explain \
    --out /tmp/tpch_query_tuning_review

CPU9 SF50 full TPC-H pilot (requested after the candidate-only preparation)
  bash auto_test/run_tpch_tuning_retest.sh --run

  Runs 176 TPC-H queries: these 31 replacements and 145 unchanged queries.
  A fresh isolated corpus and provenance are saved beside the result files.
  The launcher checks SQL hashes, SF50 row counts and candidate selectivity
  bands before testing. It uses the existing Release binary without rebuilding.
  It explicitly uses 32 threads, five timed samples (median), separate profiles,
  no full correctness comparison, and 600 seconds per execution per engine.
  It does not promote candidates or change the active 720-query benchmark.

Candidate-only command (not the requested full TPC-H run)
  OY_CORPUS="$PWD/auto_test/outerjoin_benchmark/candidates/tpch_query_tuning_20261012" \
  TPCH_SF=50 TPCH_DB="$PWD/tpch_50.duckdb" \
  bash auto_test/experiment_onoff.sh --only tpch --threads 32 --runs 5 \
    --timeout 600 --no-check-correctness --capture-plans \
    --out "auto_test/results/experiment_onoff_tpch_tuning_$(date +%Y%m%d_%H%M%S)_t32.txt"

  Only these 31 candidates run. Profiles use the existing default; warmup and
  profiling are excluded from five timed runs, whose median is reported.
  The 600-second limit applies separately to each execution on each engine.
  Either-side timeout or fallback prevents qualification as a valid selected
  measurement. The pilot does not alter the active benchmark or paper results.

Promotion requires review
  Check fresh SF50 selection, complete timing and selectivity calibration;
  do not impute old speed-ups, replace slow ratios with 1, or force a target
  abstract geomean. New IDs and SQL hashes intentionally block old-result reuse.
  Keep complete candidate outcomes, including regressions and timeouts.
  Performance-conditioned query changes must be disclosed in benchmark design;
  their gains are workload changes, not improvements to the optimizer itself.
