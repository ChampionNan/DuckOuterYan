-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q8
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT p.p_partkey AS group_key, MAX(n.n_nationkey) AS max_key
FROM (region r FULL OUTER JOIN (nation n LEFT OUTER JOIN (customer c RIGHT OUTER JOIN (orders o INNER JOIN (lineitem l FULL OUTER JOIN part p ON p.p_partkey = l.l_partkey) ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON c.c_nationkey = n.n_nationkey) ON n.n_regionkey = r.r_regionkey)
WHERE o.o_orderdate BETWEEN DATE '1993-06-01' AND DATE '1996-12-31'
GROUP BY p.p_partkey;
