-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q8
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT p.p_partkey, l.l_partkey, l.l_orderkey, o.o_orderkey, o.o_custkey, c.c_custkey, c.c_nationkey, n.n_nationkey, n.n_regionkey, r.r_regionkey
FROM (((part p LEFT OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) INNER JOIN orders o ON l.l_orderkey = o.o_orderkey) RIGHT OUTER JOIN (region r LEFT OUTER JOIN (nation n FULL OUTER JOIN customer c ON c.c_nationkey = n.n_nationkey) ON n.n_regionkey = r.r_regionkey) ON o.o_custkey = c.c_custkey)
WHERE o.o_orderdate BETWEEN DATE '1993-06-01' AND DATE '1996-12-31';
