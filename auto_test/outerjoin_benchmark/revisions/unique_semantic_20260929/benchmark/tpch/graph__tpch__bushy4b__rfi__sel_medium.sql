-- query_type: graph; family: tpch
-- source:
-- semantic_filter: tpch_supply_cost; tier=medium; supplier procurement-cost budget
-- predicate: partsupp.ps_supplycost <= 300.97
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (( region RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey) FULL OUTER JOIN ( supplier INNER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE partsupp.ps_supplycost <= 300.97;
