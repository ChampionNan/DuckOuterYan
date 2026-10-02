-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q8
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT p.p_partkey, l.l_partkey, l.l_orderkey, o.o_orderkey, o.o_custkey, c.c_custkey, c.c_nationkey, n.n_nationkey, n.n_regionkey, r.r_regionkey
FROM (((nation n INNER JOIN region r ON n.n_regionkey = r.r_regionkey) FULL OUTER JOIN customer c ON c.c_nationkey = n.n_nationkey) RIGHT OUTER JOIN (part p INNER JOIN (orders o LEFT OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) ON p.p_partkey = l.l_partkey) ON o.o_custkey = c.c_custkey)
WHERE o.o_orderdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31';
