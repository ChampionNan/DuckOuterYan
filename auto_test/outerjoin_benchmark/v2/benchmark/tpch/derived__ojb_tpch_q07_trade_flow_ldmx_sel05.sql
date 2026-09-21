-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: Supplier-to-customer trade flow with optional order and nation annotations.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=o.o_orderkey; predicate=hash(anchor) % 20 = 0
SELECT *
FROM ((((supplier s FULL OUTER JOIN lineitem l ON s.s_suppkey = l.l_suppkey) FULL OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) FULL OUTER JOIN customer c ON o.o_custkey = c.c_custkey) FULL OUTER JOIN nation n ON s.s_nationkey = n.n_nationkey)
WHERE (s.s_suppkey % 100 = 0)
  AND hash(o.o_orderkey) % 20 = 0;
