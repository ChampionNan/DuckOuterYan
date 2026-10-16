-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/tpch/queries/19222.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT p.p_partkey AS group_key, SUM(ps.ps_partkey) AS key_sum
FROM ((part p RIGHT OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) INNER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey)
WHERE ps.ps_availqty > 9700
GROUP BY p.p_partkey;
