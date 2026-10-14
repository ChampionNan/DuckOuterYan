-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q5
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM ((region r LEFT OUTER JOIN nation n ON r.r_regionkey = n.n_regionkey) RIGHT OUTER JOIN (lineitem l FULL OUTER JOIN (orders o INNER JOIN customer c ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey) ON n.n_nationkey = c.c_nationkey)
WHERE o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1994-03-15';
