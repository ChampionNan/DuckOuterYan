-- source: TPC-H Q9
-- transformation: connected join-subgraph adaptation; uniform left-deep FULL OUTER JOIN control
-- business_semantics: Part supply coverage: retain selected parts while exposing missing line-item, supplier, supply-record, and order information.
SELECT p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, ps.ps_supplycost, o.o_orderdate
FROM ((((part p FULL OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) FULL OUTER JOIN supplier s ON l.l_suppkey = s.s_suppkey) FULL OUTER JOIN partsupp ps ON ps.ps_suppkey = l.l_suppkey AND ps.ps_partkey = l.l_partkey) FULL OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey)
WHERE (p.p_name LIKE '%green%' OR p.p_partkey IS NULL);
