-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation and predicate structure unchanged
-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation graph retained; semantic filter replaced
-- semantic_filter: tpch_supply_cost; tier=low; supplier procurement-cost budget
-- predicate: partsupp.ps_supplycost <= 31.21
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (( region RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey) FULL OUTER JOIN ( supplier INNER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE partsupp.ps_supplycost <= 31.21;
