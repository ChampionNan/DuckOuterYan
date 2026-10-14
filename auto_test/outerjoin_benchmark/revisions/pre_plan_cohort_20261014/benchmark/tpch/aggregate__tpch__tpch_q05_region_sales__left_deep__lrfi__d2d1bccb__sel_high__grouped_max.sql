-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q5
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT r.r_regionkey AS group_key, MAX(o.o_custkey) AS max_key
FROM ((((nation n LEFT OUTER JOIN customer c ON n.n_nationkey = c.c_nationkey) RIGHT OUTER JOIN orders o ON c.c_custkey = o.o_custkey) FULL OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey) INNER JOIN region r ON r.r_regionkey = n.n_regionkey)
WHERE o.o_orderdate >= DATE '1992-01-01' AND o.o_orderdate < DATE '1995-08-01'
GROUP BY r.r_regionkey;
