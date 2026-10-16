-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation graph retained; semantic filter replaced
-- semantic_filter: tpch_supply_cost; tier=low; supplier procurement-cost budget
-- predicate: partsupp.ps_supplycost <= 31.21
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (( region LEFT OUTER JOIN nation ON r_regionkey = n_regionkey) RIGHT OUTER JOIN ( supplier FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE partsupp.ps_supplycost <= 31.21;
