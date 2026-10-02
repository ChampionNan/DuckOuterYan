-- query_type: graph; family: tpch
-- source:
-- semantic_filter: tpch_supply_cost; tier=low; supplier procurement-cost budget
-- predicate: partsupp.ps_supplycost <= 31.21
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT n_name, s_name, ps_availqty, p_name
FROM nation
    LEFT OUTER JOIN supplier ON n_nationkey = s_nationkey
    RIGHT OUTER JOIN partsupp  ON s_suppkey = ps_suppkey
    FULL OUTER JOIN part      ON ps_partkey = p_partkey
WHERE partsupp.ps_supplycost <= 31.21;
