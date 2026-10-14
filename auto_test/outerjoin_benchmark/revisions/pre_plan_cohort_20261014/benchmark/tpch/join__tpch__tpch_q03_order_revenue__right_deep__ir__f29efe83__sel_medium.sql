-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q3
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT c.c_custkey, o.o_custkey, o.o_orderkey, l.l_orderkey
FROM (lineitem l INNER JOIN (orders o RIGHT OUTER JOIN customer c ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE o.o_orderdate < DATE '1994-01-01';
