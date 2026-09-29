-- query_type: join; family: tpch
-- source: TPC-H Q5
-- semantic_filter: tpch_q05_period; tier=high; TPC-H Q5 order reporting period
-- predicate: o.o_orderdate >= DATE '1992-01-01' AND o.o_orderdate < DATE '1996-01-01'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM (((nation n FULL OUTER JOIN region r ON r.r_regionkey = n.n_regionkey) INNER JOIN customer c ON n.n_nationkey = c.c_nationkey) LEFT OUTER JOIN (lineitem l RIGHT OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey) ON c.c_custkey = o.o_custkey)
WHERE o.o_orderdate >= DATE '1992-01-01' AND o.o_orderdate < DATE '1996-01-01';
