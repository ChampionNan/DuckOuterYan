Frozen TPC-H candidate definitions

This directory contains 31 replacement SQL definitions. The current benchmark
adopts the 20 identities pinned by sources/tpch_tuning_promotion_20261013.json.
The remaining queries are candidates, not additional active benchmark entries.

Selection was performance-conditioned. That provenance and the frozen selection
rules remain explicit, but historical timing and correctness outputs are not
published with these query inputs. Each new query requires fresh measurement.

manifest.csv identifies candidate SQL and predicate calibration parameters.
replacement_map.csv maps original and candidate identities without timings.
proposed_full_manifest.csv records the proposed workload membership.
queries.txt and baseline_queries.txt are runner input lists.

Local EXPLAIN decisions, pilot comparisons, and environment/proposal reports are
ignored outputs. New reports belong under auto_test/results/ or outside the
repository. Use the main auto_test README for execution and output policy.
