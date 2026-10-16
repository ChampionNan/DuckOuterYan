-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q9
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, ps.ps_supplycost, o.o_orderdate
FROM ((((lineitem l LEFT OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey) INNER JOIN partsupp ps ON ps.ps_suppkey = l.l_suppkey AND ps.ps_partkey = l.l_partkey) FULL OUTER JOIN supplier s ON l.l_suppkey = s.s_suppkey) RIGHT OUTER JOIN part p ON p.p_partkey = l.l_partkey)
WHERE p.p_name LIKE '%green%';
