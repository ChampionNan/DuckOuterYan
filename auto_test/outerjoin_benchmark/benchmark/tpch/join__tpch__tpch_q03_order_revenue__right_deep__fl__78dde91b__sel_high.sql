-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q3
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT c.c_custkey, o.o_custkey, o.o_orderkey, l.l_orderkey
FROM (customer c FULL OUTER JOIN (lineitem l LEFT OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey) ON c.c_custkey = o.o_custkey)
WHERE o.o_orderdate < DATE '1995-03-15';
