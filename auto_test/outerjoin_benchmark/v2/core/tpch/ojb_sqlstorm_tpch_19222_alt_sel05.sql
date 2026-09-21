-- source: SQLStorm v1.0/tpch/queries/19222.sql
-- transformation: connected join-subgraph adaptation; alternate mixed form; bushy grouping is structurally ineligible
-- business_semantics: Part-supplier coverage adapted from SQLStorm: selected parts remain visible when a supply or supplier record is missing.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=ps.ps_partkey; predicate=hash(anchor) % 20 = 0
SELECT p.p_name, s.s_name, ps.ps_availqty
FROM ((part p FULL OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) RIGHT OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey)
WHERE (p.p_partkey <= 1000)
  AND hash(ps.ps_partkey) % 20 = 0;
