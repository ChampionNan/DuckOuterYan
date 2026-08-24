-- source: TPC-H Q9
-- transformation: connected join-subgraph adaptation; right-deep FULL-outer applicability form
-- business_semantics: Part supply coverage: retain selected parts while exposing missing line-item, supplier, supply-record, and order information.
SELECT p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, ps.ps_supplycost, o.o_orderdate
FROM (orders o FULL OUTER JOIN (partsupp ps FULL OUTER JOIN (supplier s FULL OUTER JOIN (lineitem l FULL OUTER JOIN part p ON p.p_partkey = l.l_partkey) ON l.l_suppkey = s.s_suppkey) ON ps.ps_suppkey = l.l_suppkey) ON o.o_orderkey = l.l_orderkey)
WHERE p.p_name LIKE '%green%';
