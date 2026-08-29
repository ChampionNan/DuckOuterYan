-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- transformation: connected join-subgraph adaptation; secondary cross-product-free bushy FULL-outer applicability form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM ((part p FULL OUTER JOIN ((orders o FULL OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) FULL OUTER JOIN customer c ON o.o_custkey = c.c_custkey) ON p.p_partkey = l.l_partkey) FULL OUTER JOIN (supplier s FULL OUTER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey)
WHERE p.p_partkey % 1000 = 0;
