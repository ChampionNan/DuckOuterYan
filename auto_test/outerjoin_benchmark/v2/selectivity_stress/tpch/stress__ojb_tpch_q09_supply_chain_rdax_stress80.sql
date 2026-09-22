-- source: TPC-H Q9
-- transformation: connected join-subgraph adaptation; balanced mixed secondary right-deep source-derived form
-- business_semantics: Part supply coverage: retain selected parts while exposing missing line-item, supplier, supply-record, and order information.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress80; approximately 80% of hash buckets; anchor=l.l_suppkey; predicate=hash(l.l_suppkey) % 4000 < 3200
SELECT p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, ps.ps_supplycost, o.o_orderdate
FROM (orders o RIGHT OUTER JOIN (partsupp ps LEFT OUTER JOIN (part p FULL OUTER JOIN (lineitem l INNER JOIN supplier s ON l.l_suppkey = s.s_suppkey) ON p.p_partkey = l.l_partkey) ON ps.ps_suppkey = l.l_suppkey) ON o.o_orderkey = l.l_orderkey)
WHERE (p.p_name LIKE '%green%')
  AND hash(l.l_suppkey) % 4000 < 3200;
