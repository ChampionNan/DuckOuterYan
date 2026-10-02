-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT p.p_partkey, ps.ps_partkey, ps.ps_suppkey, s.s_suppkey, l.l_partkey
FROM (((partsupp ps INNER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) LEFT OUTER JOIN part p ON p.p_partkey = ps.ps_partkey) RIGHT OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey)
WHERE l.l_shipdate BETWEEN DATE '1994-06-01' AND DATE '1997-12-31';
