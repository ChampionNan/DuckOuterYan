-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q5
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM ((((region r INNER JOIN nation n ON r.r_regionkey = n.n_regionkey) RIGHT OUTER JOIN customer c ON n.n_nationkey = c.c_nationkey) FULL OUTER JOIN orders o ON c.c_custkey = o.o_custkey) LEFT OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey)
WHERE o.o_orderdate >= DATE '1992-01-01' AND o.o_orderdate < DATE '1995-08-01';
