-- query_type: graph; family: tpch
-- source:
-- semantic_filter: tpch_supply_cost; tier=low; supplier procurement-cost budget
-- predicate: partsupp.ps_supplycost <= 31.21
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM region INNER JOIN (nation LEFT OUTER JOIN (supplier RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey) ON r_regionkey = n_regionkey
WHERE partsupp.ps_supplycost <= 31.21;
