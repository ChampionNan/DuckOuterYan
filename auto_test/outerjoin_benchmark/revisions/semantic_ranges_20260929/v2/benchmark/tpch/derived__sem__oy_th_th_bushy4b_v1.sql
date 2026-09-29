-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FIL; relation and predicate structure unchanged
-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation graph retained; semantic filter replaced
-- semantic_filter: tpch_supply_cost; tier=medium; supplier procurement-cost budget
-- predicate: partsupp.ps_supplycost <= 300.97
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (( region FULL OUTER JOIN nation ON r_regionkey = n_regionkey) INNER JOIN ( supplier LEFT OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE partsupp.ps_supplycost <= 300.97;
