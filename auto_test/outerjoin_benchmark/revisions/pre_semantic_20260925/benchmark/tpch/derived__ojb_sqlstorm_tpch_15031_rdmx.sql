-- source: SQLStorm v1.0/tpch/queries/15031.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM (supplier s FULL OUTER JOIN (partsupp ps RIGHT OUTER JOIN part p ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey)
WHERE p.p_partkey % 1000 = 0;
