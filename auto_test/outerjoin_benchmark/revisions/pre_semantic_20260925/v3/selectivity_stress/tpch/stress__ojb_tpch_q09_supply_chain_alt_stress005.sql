-- source: TPC-H Q9
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: Part supply coverage: retain selected parts while exposing missing line-item, supplier, supply-record, and order information.
-- corpus_version: v3
-- derived_from_corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress005; approximately 0.05% of hash buckets; anchor=l.l_suppkey; predicate=hash(l.l_suppkey) % 4000 < 2
SELECT p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, ps.ps_supplycost, o.o_orderdate
FROM ((((part p RIGHT OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) FULL OUTER JOIN supplier s ON l.l_suppkey = s.s_suppkey) INNER JOIN partsupp ps ON ps.ps_suppkey = l.l_suppkey) LEFT OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey)
WHERE (p.p_name LIKE '%green%')
  AND hash(l.l_suppkey) % 4000 < 2;
