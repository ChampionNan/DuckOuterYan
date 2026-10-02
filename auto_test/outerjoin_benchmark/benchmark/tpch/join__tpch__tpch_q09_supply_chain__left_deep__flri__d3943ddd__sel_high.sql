-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q9
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, ps.ps_supplycost, o.o_orderdate
FROM ((((lineitem l FULL OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey) LEFT OUTER JOIN partsupp ps ON ps.ps_suppkey = l.l_suppkey AND ps.ps_partkey = l.l_partkey) RIGHT OUTER JOIN supplier s ON l.l_suppkey = s.s_suppkey) INNER JOIN part p ON p.p_partkey = l.l_partkey)
WHERE (p.p_name LIKE '%green%' OR p.p_name LIKE '%blue%' OR p.p_name LIKE '%red%' OR p.p_name LIKE '%yellow%' OR p.p_name LIKE '%orange%' OR p.p_name LIKE '%purple%' OR p.p_name LIKE '%white%' OR p.p_name LIKE '%black%' OR p.p_name LIKE '%pink%' OR p.p_name LIKE '%brown%' OR p.p_name LIKE '%gray%');
