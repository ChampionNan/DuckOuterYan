-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q8
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT p.p_partkey, l.l_partkey, l.l_orderkey, o.o_orderkey, o.o_custkey, c.c_custkey, c.c_nationkey, n.n_nationkey, n.n_regionkey, r.r_regionkey
FROM (((((lineitem l RIGHT OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) LEFT OUTER JOIN customer c ON o.o_custkey = c.c_custkey) FULL OUTER JOIN nation n ON c.c_nationkey = n.n_nationkey) INNER JOIN region r ON n.n_regionkey = r.r_regionkey) INNER JOIN part p ON p.p_partkey = l.l_partkey)
WHERE o.o_orderdate BETWEEN DATE '1995-01-01' AND DATE '1995-03-15';
