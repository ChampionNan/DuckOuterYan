-- source: TPC-H Q9
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: Part supply coverage: retain selected parts while exposing missing line-item, supplier, supply-record, and order information.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, ps.ps_supplycost, o.o_orderdate
FROM (part p INNER JOIN (supplier s LEFT OUTER JOIN (partsupp ps RIGHT OUTER JOIN (lineitem l FULL OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey) ON ps.ps_suppkey = l.l_suppkey) ON l.l_suppkey = s.s_suppkey) ON p.p_partkey = l.l_partkey)
WHERE p.p_name LIKE '%green%';
