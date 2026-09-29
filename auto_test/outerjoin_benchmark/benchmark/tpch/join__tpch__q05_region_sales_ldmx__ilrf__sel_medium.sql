-- query_type: join; family: tpch
-- source: TPC-H Q5
-- semantic_filter: tpch_q05_period; tier=medium; TPC-H Q5 order reporting period
-- predicate: o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1995-01-01'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM ((((region r INNER JOIN nation n ON r.r_regionkey = n.n_regionkey) LEFT OUTER JOIN customer c ON n.n_nationkey = c.c_nationkey) RIGHT OUTER JOIN orders o ON c.c_custkey = o.o_custkey) FULL OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey)
WHERE o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1995-01-01';
