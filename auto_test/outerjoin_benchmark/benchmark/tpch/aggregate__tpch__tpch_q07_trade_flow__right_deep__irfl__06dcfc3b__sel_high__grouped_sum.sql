-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q7
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT s.s_suppkey AS group_key, SUM(o.o_orderkey) AS key_sum
FROM (nation n INNER JOIN (supplier s RIGHT OUTER JOIN (customer c FULL OUTER JOIN (orders o LEFT OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON s.s_suppkey = l.l_suppkey) ON s.s_nationkey = n.n_nationkey)
WHERE l.l_shipdate BETWEEN DATE '1993-06-01' AND DATE '1996-12-31'
GROUP BY s.s_suppkey;
