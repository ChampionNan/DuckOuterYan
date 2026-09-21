-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=ps.ps_partkey; predicate=hash(anchor) % 100 = 0
SELECT *
FROM (((part p FULL OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) FULL OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) FULL OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey)
WHERE (p.p_partkey % 1000 = 0)
  AND hash(ps.ps_partkey) % 100 = 0;
