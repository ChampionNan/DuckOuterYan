# Retired FULL-heavy corpus: multithread timeout exclusions

> Historical record only. The current default revision is
> `v1-mixed-graph25-20260925`, contains all **224 queries** (including the full
> 25-pattern Graph control set), and has no active timeout exclusions. The
> tables below describe the preceding 206-query revision. Changing join labels
> changed the SQL and invalidated those timeout and performance observations. A
> complete current-v1 run is required before defining any new exclusions.

The retired FULL-heavy active corpus contained 176 queries, down from 206
originally and 185 after the first timeout filter. This record explains the
nine explicit 32-thread removals. No successful query, including an OuterYan
regression or a DuckDB-selected control, was removed to improve the score or
rebalance counts. The full 170-query core and 36-query evaluation components
retained all source SQL.

## Evidence and scope

The first filter excluded 21 OFF correctness-gate timeouts from
`experiment_onoff_benchmark_20260830_002656`, at 48 threads and 1800 seconds.

The new evidence is `experiment_onoff_benchmark_20260908_235240_t32.csv`, its
attempts CSV, and TXT log under `auto_test/results/`. Both CSVs have 185 rows
and are identical; final/attempts deduplication gives 185 queries, not 370.
Nine have `note=TIMEOUT`. Every matching log block says
`TIMEOUT (1800s, off)`: **OFF correctness timed out; ON execution/timing was
not reached.** This does not establish an OuterYan timeout or incorrectness.

The user explicitly authorized removing all nine 32-thread timeouts, overriding
the previous exceptions for graph bushy and TPC-H Q9 star:

| Active query (all names start with `derived__`) | Family | Tree shape | Join graph | Relations |
|---|---|---|---|---:|
| bushy_N5_mixA_s01 | graph | bushy | chain | 5 |
| bushy_N5_mixC_s01 | graph | bushy | chain | 5 |
| ojb_tpch_q09_supply_chain_alt | TPC-H | left-deep | star | 5 |
| ojb_tpch_q09_supply_chain_ldmx | TPC-H | left-deep | star | 5 |
| ojb_tpch_q09_supply_chain_rdax | TPC-H | right-deep | star | 5 |
| ojb_tpch_q09_supply_chain_rdmx | TPC-H | right-deep | star | 5 |
| ojb_tpch_q09_supply_chain_rduL | TPC-H | right-deep | star | 5 |
| ojb_tpcds_q93_return_reason_ldmx | TPC-DS | left-deep | chain | 3 |
| ojb_tpcds_q93_return_reason_rdax | TPC-DS | right-deep | chain | 3 |

Core shape/topology/relation labels come from the source manifest. The graph
cases have five relation instances connected by a chain of ON equalities,
despite their bushy join-tree grouping. These two dimensions are not synonyms.

## Coverage before and after

| Family | Original active | After 48-thread filter | Current active | Newly removed |
|---|---:|---:|---:|---:|
| graph | 7 | 7 | 5 | 2 |
| TPC-H | 54 | 53 | 48 | 5 |
| TPC-DS | 63 | 43 | 41 | 2 |
| JOB | 82 | 82 | 82 | 0 |
| Total | 206 | 185 | 176 | 9 |

The active core changes from 151 to 144; evaluation from 34 to 32.

| Core dimension | Category | Original 170 | Previous 151 | Current 144 |
|---|---|---:|---:|---:|
| Tree shape | left-deep | 46 | 41 | 38 |
| Tree shape | right-deep | 80 | 70 | 66 |
| Tree shape | bushy | 44 | 40 | 40 |
| Join graph | chain | 65 | 59 | 57 |
| Join graph | star | 30 | 27 | 22 |
| Join graph | branch | 75 | 65 | 65 |
| Relations | 3 | 30 | 24 | 22 |
| Relations | 4 | 20 | 20 | 20 |
| Relations | 5 | 95 | 82 | 77 |
| Relations | 6 | 25 | 25 | 25 |

All overall core categories remain represented. Relative to the original core,
the maximum absolute share shifts are 1.90 percentage points for tree shape,
2.37 for topology, and 2.66 each for relation count and join vector (rounded up).
The generator retains the original 2 pp tree-shape bound and now permits 3 pp
for the other dimensions to accommodate the explicitly approved timeouts.

**Coverage is not fully preserved.** The active graph family now contains only
right-deep cases; its bushy cases remain in the evaluation component but are
not timed by the default harness. TPC-H loses its only core star seed (Q9), and
its associated mixed `FRIL` join-vector category. Other families still cover
star and bushy inputs. The generator records exactly the approved missing
core family/topology and family/join-vector categories and rejects any additional
loss. Family weights, source-seed bundles, and within-family proportions are not
claimed to be unchanged. Do not present this as a fully pattern-balanced corpus.

## Reporting and recovery

The nine timeouts already had no valid OFF/ON pair. Removing them from the
future workload does not change the 0908 complete-case score:
176 measured queries, geomean 1.206138x, total-time ratio 1.341119x. Retain the
historical 185-query coverage and its nine failures in that run's statistics.
Do not impute 1800-second runtimes or count timeout removal as a measured speedup.

`../benchmark_timeouts.py` pins all 30 excluded paths and current component
SQL hashes. Per-query metadata identifies the 21 older 48-thread exclusions and
nine newly confirmed 32-thread exclusions separately. Generation never reads
machine-local result files. The historical logs contain no SQL hashes; the
pins protect the current local source bytes, not proof of server byte identity.

The historical exclusion metadata remains in `../benchmark_timeouts.py`.
`active_timeout_exclusions.csv` is intentionally empty for the current mixed
revision. The 84 still older historical exclusions remain in
`timeout_exclusions.csv`. No source SQL or raw result was deleted.

This update used generation, hash validation and lightweight tests only.
No large-data query or new performance experiment was run on the laptop.
