-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q7
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT s.s_suppkey, l.l_suppkey, l.l_orderkey, o.o_orderkey, o.o_custkey, c.c_custkey, s.s_nationkey, n.n_nationkey
FROM ((supplier s FULL OUTER JOIN nation n ON s.s_nationkey = n.n_nationkey) LEFT OUTER JOIN (customer c RIGHT OUTER JOIN (orders o INNER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON s.s_suppkey = l.l_suppkey)
WHERE l.l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31';
