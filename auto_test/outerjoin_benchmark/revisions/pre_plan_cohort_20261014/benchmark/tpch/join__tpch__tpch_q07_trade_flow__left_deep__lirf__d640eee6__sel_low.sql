-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q7
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT s.s_suppkey, l.l_suppkey, l.l_orderkey, o.o_orderkey, o.o_custkey, c.c_custkey, s.s_nationkey, n.n_nationkey
FROM ((((lineitem l LEFT OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) INNER JOIN customer c ON o.o_custkey = c.c_custkey) RIGHT OUTER JOIN supplier s ON s.s_suppkey = l.l_suppkey) FULL OUTER JOIN nation n ON s.s_nationkey = n.n_nationkey)
WHERE l.l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1995-03-15';
