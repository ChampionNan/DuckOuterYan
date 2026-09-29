-- source: SQLStorm v1.0/tpch/queries/19222.sql
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: Part-supplier coverage adapted from SQLStorm: selected parts remain visible when a supply or supplier record is missing.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=ps.ps_partkey; predicate=hash(anchor) % 100 = 0
SELECT p.p_name, s.s_name, ps.ps_availqty
FROM (part p INNER JOIN (partsupp ps LEFT OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey)
WHERE (p.p_partkey <= 1000)
  AND hash(ps.ps_partkey) % 100 = 0;
