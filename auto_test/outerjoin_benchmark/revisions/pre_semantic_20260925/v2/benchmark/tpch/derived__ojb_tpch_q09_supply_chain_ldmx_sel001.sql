-- source: TPC-H Q9
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Part supply coverage: retain selected parts while exposing missing line-item, supplier, supply-record, and order information.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=l.l_suppkey; predicate=hash(anchor) % 1000 = 0
SELECT p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, ps.ps_supplycost, o.o_orderdate
FROM ((((part p INNER JOIN lineitem l ON p.p_partkey = l.l_partkey) LEFT OUTER JOIN supplier s ON l.l_suppkey = s.s_suppkey) RIGHT OUTER JOIN partsupp ps ON ps.ps_suppkey = l.l_suppkey) FULL OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey)
WHERE (p.p_name LIKE '%green%')
  AND hash(l.l_suppkey) % 1000 = 0;
