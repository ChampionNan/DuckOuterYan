-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q7
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT s.s_suppkey AS group_key, MIN(o.o_orderkey) AS min_key
FROM ((((supplier s LEFT OUTER JOIN lineitem l ON s.s_suppkey = l.l_suppkey) RIGHT OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) FULL OUTER JOIN customer c ON o.o_custkey = c.c_custkey) INNER JOIN nation n ON s.s_nationkey = n.n_nationkey)
WHERE l.l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1995-03-15'
GROUP BY s.s_suppkey;
