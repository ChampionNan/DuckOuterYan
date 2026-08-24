-- source: SQLStorm v1.0/tpch/queries/19222.sql
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: Part-supplier coverage adapted from SQLStorm: selected parts remain visible when a supply or supplier record is missing.
SELECT p.p_name, s.s_name, ps.ps_availqty
FROM ((supplier s FULL OUTER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) FULL OUTER JOIN part p ON p.p_partkey = ps.ps_partkey)
WHERE p.p_partkey <= 1000;
