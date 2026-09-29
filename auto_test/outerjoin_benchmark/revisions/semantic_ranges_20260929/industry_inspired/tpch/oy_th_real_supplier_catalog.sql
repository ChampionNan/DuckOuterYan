-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFIL; relation graph retained; semantic filter replaced
-- semantic_filter: tpch_supply_cost; tier=high; supplier procurement-cost budget
-- predicate: partsupp.ps_supplycost <= 550.19
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT s_name, n_name, r_name, p_name, ps_availqty
FROM supplier
    RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
    FULL OUTER JOIN part     ON ps_partkey = p_partkey
    INNER JOIN nation   ON s_nationkey = n_nationkey
    LEFT OUTER JOIN region   ON n_regionkey = r_regionkey
WHERE partsupp.ps_supplycost <= 550.19;
