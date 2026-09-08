# Active corpus: multithread timeout exclusions

The default corpus contains **185 queries**, down from 206. Only 21 confirmed
multithread timeout cases are excluded; no successful query is removed to make
the counts equal. The complete 170-query `core/` and 36-query
`industry_inspired/` component views remain unchanged and retain the source SQL.

## Evidence and scope

The reference is `experiment_onoff_benchmark_20260830_002656.csv` and its `.txt`
log under `auto_test/results/`. Matching their query paths identifies 28 explicit
`note=TIMEOUT` cases at the **OFF correctness gate, 48 threads, 1800 seconds**.
ON timing was not reached for those cases; this is not evidence that both modes
timed out. It is one historical observation, not a new 16/32-thread retest.
The 14 queries with complete multithread timing but missing single-thread timing
are retained. Missing values alone are not a timeout criterion.

The user requested retaining two otherwise-lost patterns, so seven of the 28
remain active:

- Graph bushy: `derived__bushy_N5_mixA_s01` and `derived__bushy_N5_mixC_s01`.
- TPC-H core star: all five `derived__ojb_tpch_q09_supply_chain_*` variants
  (`alt`, `ldmx`, `rdax`, `rdmx`, `rduL`).

These are coverage exceptions and **can still time out** in the default run.
The other 21 comprise 19 TPC-DS core queries and two industry-inspired queries
(TPC-H customer activity detail and TPC-DS store activity detail).

## Coverage before and after

| Family | Original active | Filtered active | Removed |
|---|---:|---:|---:|
| graph | 7 | 7 | 0 |
| TPC-H | 54 | 53 | 1 |
| TPC-DS | 63 | 43 | 20 |
| JOB | 82 | 82 | 0 |
| Total | 206 | 185 | 21 |

The core subset changes from 170 to 151; the evaluation subset from 36 to 34.
The following distributions apply to the **core**, whose manifest explicitly
records tree shape, topology, relation count, and join vector:

| Dimension | Category | Original core | Active core |
|---|---|---:|---:|
| Tree shape | left-deep | 46 | 41 |
| Tree shape | right-deep | 80 | 70 |
| Tree shape | bushy | 44 | 40 |
| Join topology | chain | 65 | 59 |
| Join topology | star | 30 | 27 |
| Join topology | branch | 75 | 65 |
| Relations | 3 | 30 | 24 |
| Relations | 4 | 20 | 20 |
| Relations | 5 | 95 | 82 |
| Relations | 6 | 25 | 25 |

All existing core categories, including join-vector categories and each
family/category combination, remain represented. The largest absolute change
in an overall core category's share is 0.71 percentage points for tree shape,
1.08 for topology, 1.86 for relation count, and 1.88 for join vector (rounded up).
Generation enforces coverage plus a two-percentage-point limit for these
overall core distributions, and explicitly protects the seven exceptions.

This preserves pattern coverage and approximately preserves overall core
pattern proportions; it does **not** preserve benchmark family weights, every
seed, every five-variant bundle, or within-family pattern proportions exactly.
TPC-DS is affected most. Report the filtered membership and excluded cases
alongside speedups; do not compare an old 206-query aggregate directly with a
new 185-query aggregate or count timeouts as measured speedups. Supplemental
legacy performance-selected cases remain unsuitable for an unbiased headline
score.

## Reproducibility and recovery

`../benchmark_timeouts.py` pins the 21 active query paths and current component
SQL hashes, together with the seven protected paths. Generation reads this
checked-in metadata, **never the local results CSV**. Hashes pin the SQL being
excluded now; the historical run did not record SQL hashes, so they do not prove
the server executed identical bytes. Changed excluded SQL requires explicit
review before regeneration.

`active_timeout_exclusions.csv` records each removed active path, retained
component source path, content hash, and reference timeout information. This is
separate from `timeout_exclusions.csv`, which records the older 84 historical
corpus exclusions. No source SQL or experiment result is deleted. To restore a
case after review, update the pinned policy and expected counts/coverage tests,
then regenerate. Running a complete component directory intentionally bypasses
this active-view filter.

Validation here is generation and static coverage testing only. No large-data
query or new performance test was run on the laptop.
