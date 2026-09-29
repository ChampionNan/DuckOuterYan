-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v3
-- derived_from_corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress0025; approximately 0.025% of hash buckets; anchor=o.o_orderkey; predicate=hash(o.o_orderkey) % 4000 < 1
SELECT *
FROM (customer c LEFT OUTER JOIN (orders o INNER JOIN (lineitem l FULL OUTER JOIN (supplier s RIGHT OUTER JOIN (partsupp ps LEFT OUTER JOIN part p ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = l.l_partkey) ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey)
WHERE (p.p_partkey % 1000 = 0)
  AND hash(o.o_orderkey) % 4000 < 1;
