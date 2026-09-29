-- query_type: join; family: tpch
-- source: TPC-H Q8
-- semantic_filter: tpch_q08_period; tier=low; TPC-H Q8 order reporting period
-- predicate: o.o_orderdate BETWEEN DATE '1995-01-01' AND DATE '1995-03-15'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (part p FULL OUTER JOIN (lineitem l INNER JOIN (orders o LEFT OUTER JOIN (customer c RIGHT OUTER JOIN (nation n FULL OUTER JOIN region r ON n.n_regionkey = r.r_regionkey) ON c.c_nationkey = n.n_nationkey) ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey) ON p.p_partkey = l.l_partkey)
WHERE o.o_orderdate BETWEEN DATE '1995-01-01' AND DATE '1995-03-15';
