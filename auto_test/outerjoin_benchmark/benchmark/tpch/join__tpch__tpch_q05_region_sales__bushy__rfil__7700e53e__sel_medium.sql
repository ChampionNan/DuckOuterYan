-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q5
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM ((region r RIGHT OUTER JOIN nation n ON r.r_regionkey = n.n_regionkey) FULL OUTER JOIN (lineitem l INNER JOIN (orders o LEFT OUTER JOIN customer c ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey) ON n.n_nationkey = c.c_nationkey)
WHERE o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1995-01-01';
