# Frozen exact-query retirements (20261009)

This cumulative archive preserves the nine 20261008 removals and the one
Graph low-selectivity global COUNT query explicitly removed on 20261009.
The active generator pins `sources/retirements_20261009.json`; the previous
policy and archive are unchanged. Only the low version is newly removed.
Medium/high versions remain active. Raw measurement CSVs are not changed.

The new query ran in 8.518565 ms (DuckDB) and 17.436539 ms (OuterYan),
using five-run medians. This is a user-requested workload change after
observing performance, not an optimizer improvement or evidence that all
other short queries are stable. No repeated-run variance is inferred.
