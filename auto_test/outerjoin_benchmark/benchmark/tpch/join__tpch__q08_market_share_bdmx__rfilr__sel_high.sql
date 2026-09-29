-- query_type: join; family: tpch
-- source: TPC-H Q8
-- semantic_filter: tpch_q08_period; tier=high; TPC-H Q8 order reporting period
-- predicate: o.o_orderdate BETWEEN DATE '1993-01-01' AND DATE '1996-12-31'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((lineitem l RIGHT OUTER JOIN part p ON p.p_partkey = l.l_partkey) FULL OUTER JOIN (orders o INNER JOIN ((nation n LEFT OUTER JOIN customer c ON c.c_nationkey = n.n_nationkey) RIGHT OUTER JOIN region r ON n.n_regionkey = r.r_regionkey) ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey)
WHERE o.o_orderdate BETWEEN DATE '1993-01-01' AND DATE '1996-12-31';
