-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/tpch/queries/19222.sql
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT p.p_name, s.s_name, ps.ps_availqty
FROM (part p RIGHT OUTER JOIN (supplier s LEFT OUTER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey)
WHERE ps.ps_availqty > 4500;
