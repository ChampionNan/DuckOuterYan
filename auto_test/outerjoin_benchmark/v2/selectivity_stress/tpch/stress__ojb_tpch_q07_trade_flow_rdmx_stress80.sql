-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; right-deep FULL-outer applicability form
-- business_semantics: Supplier-to-customer trade flow with optional order and nation annotations.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress80; approximately 80% of hash buckets; anchor=s.s_suppkey; predicate=hash(s.s_suppkey) % 4000 < 3200
SELECT *
FROM (nation n FULL OUTER JOIN (customer c FULL OUTER JOIN (orders o FULL OUTER JOIN (lineitem l FULL OUTER JOIN supplier s ON s.s_suppkey = l.l_suppkey) ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON s.s_nationkey = n.n_nationkey)
WHERE hash(s.s_suppkey) % 4000 < 3200;
