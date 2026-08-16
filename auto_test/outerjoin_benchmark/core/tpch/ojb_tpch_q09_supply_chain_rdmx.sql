-- source: TPC-H Q9
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: Part supply coverage: retain selected parts while exposing missing line-item, supplier, supply-record, and order information.
SELECT p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, ps.ps_supplycost, o.o_orderdate
FROM (orders o RIGHT OUTER JOIN (partsupp ps FULL OUTER JOIN (supplier s RIGHT OUTER JOIN (lineitem l RIGHT OUTER JOIN part p ON p.p_partkey = l.l_partkey) ON l.l_suppkey = s.s_suppkey) ON ps.ps_suppkey = l.l_suppkey AND ps.ps_partkey = l.l_partkey) ON o.o_orderkey = l.l_orderkey)
WHERE (p.p_name LIKE '%green%' OR p.p_partkey IS NULL);
