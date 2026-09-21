-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=ps.ps_partkey; predicate=hash(anchor) % 100 = 0
SELECT *
FROM (supplier s FULL OUTER JOIN (partsupp ps FULL OUTER JOIN (part p FULL OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey)
WHERE (p.p_partkey % 1000 = 0)
  AND hash(ps.ps_partkey) % 100 = 0;
