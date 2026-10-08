-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT p.p_partkey AS group_key, MAX(o.o_orderkey) AS max_key
FROM (((part p LEFT OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) FULL OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) INNER JOIN (customer c LEFT OUTER JOIN (orders o RIGHT OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON p.p_partkey = l.l_partkey)
WHERE o.o_orderdate BETWEEN DATE '1996-01-01' AND DATE '1996-03-15'
GROUP BY p.p_partkey;
