-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress10; approximately 10% of hash buckets; anchor=p.p_partkey; predicate=hash(p.p_partkey) % 4000 < 400
SELECT *
FROM (supplier s FULL OUTER JOIN (partsupp ps FULL OUTER JOIN (part p FULL OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey)
WHERE hash(p.p_partkey) % 4000 < 400;
