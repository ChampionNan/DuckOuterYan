-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation and predicate structure unchanged
-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FIL; relation graph retained; semantic filter replaced
-- semantic_filter: tpch_supply_cost; tier=low; supplier procurement-cost budget
-- predicate: partsupp.ps_supplycost <= 31.21
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT n_name, s_name, ps_availqty, p_name
FROM nation
    LEFT OUTER JOIN supplier ON n_nationkey = s_nationkey
    RIGHT OUTER JOIN partsupp  ON s_suppkey = ps_suppkey
    FULL OUTER JOIN part      ON ps_partkey = p_partkey
WHERE partsupp.ps_supplycost <= 31.21;
