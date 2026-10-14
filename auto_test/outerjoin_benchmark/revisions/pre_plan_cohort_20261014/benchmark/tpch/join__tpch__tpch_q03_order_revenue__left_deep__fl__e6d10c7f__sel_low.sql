-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q3
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT c.c_custkey, o.o_custkey, o.o_orderkey, l.l_orderkey
FROM ((customer c FULL OUTER JOIN orders o ON c.c_custkey = o.o_custkey) LEFT OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey)
WHERE o.o_orderdate < DATE '1992-03-15';
