-- query_type: aggregate; family: tpch
-- source: TPC-H Q5
-- semantic_filter: tpch_q05_period; tier=low; TPC-H Q5 order reporting period
-- predicate: o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1994-03-15'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT r.r_regionkey AS group_key, SUM(o.o_custkey) AS key_sum
FROM (lineitem l INNER JOIN (orders o FULL OUTER JOIN (customer c RIGHT OUTER JOIN (nation n LEFT OUTER JOIN region r ON r.r_regionkey = n.n_regionkey) ON n.n_nationkey = c.c_nationkey) ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1994-03-15'
GROUP BY r.r_regionkey;
