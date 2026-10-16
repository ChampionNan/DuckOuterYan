-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM ((supplier s LEFT OUTER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) INNER JOIN (lineitem l RIGHT OUTER JOIN part p ON p.p_partkey = l.l_partkey) ON p.p_partkey = ps.ps_partkey)
WHERE p.p_partkey % 1000 = 0;
