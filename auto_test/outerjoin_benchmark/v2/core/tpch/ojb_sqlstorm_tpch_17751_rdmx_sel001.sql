-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- transformation: connected join-subgraph adaptation; right-deep FULL-outer applicability form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=ps.ps_partkey; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM (lineitem l FULL OUTER JOIN (supplier s FULL OUTER JOIN (partsupp ps FULL OUTER JOIN part p ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = l.l_partkey)
WHERE (p.p_partkey % 1000 = 0)
  AND hash(ps.ps_partkey) % 1000 = 0;
