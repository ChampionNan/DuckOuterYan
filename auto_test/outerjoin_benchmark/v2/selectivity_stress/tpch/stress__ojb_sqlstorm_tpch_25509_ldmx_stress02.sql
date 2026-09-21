-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress02; approximately 0.2% of hash buckets; anchor=p.p_partkey; predicate=hash(p.p_partkey) % 4000 < 8
SELECT *
FROM (((((part p FULL OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) FULL OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) FULL OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) FULL OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) FULL OUTER JOIN customer c ON o.o_custkey = c.c_custkey)
WHERE hash(p.p_partkey) % 4000 < 8;
