-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT p.p_partkey, ps.ps_partkey, ps.ps_suppkey, s.s_suppkey, l.l_partkey, l.l_orderkey, o.o_orderkey, o.o_custkey, c.c_custkey
FROM (((((partsupp ps RIGHT OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) LEFT OUTER JOIN part p ON p.p_partkey = ps.ps_partkey) INNER JOIN lineitem l ON p.p_partkey = l.l_partkey) FULL OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) LEFT OUTER JOIN customer c ON o.o_custkey = c.c_custkey)
WHERE o.o_orderdate BETWEEN DATE '1996-01-01' AND DATE '1996-03-15';
