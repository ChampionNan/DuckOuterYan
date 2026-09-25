-- source: TPC-H Q9
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Part supply coverage: retain selected parts while exposing missing line-item, supplier, supply-record, and order information.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_max; anchor=l.l_suppkey; group_key=p.p_partkey
SELECT p.p_partkey AS group_key, MAX(l.l_suppkey) AS max_key
FROM (orders o INNER JOIN (partsupp ps FULL OUTER JOIN (supplier s RIGHT OUTER JOIN (lineitem l LEFT OUTER JOIN part p ON p.p_partkey = l.l_partkey) ON l.l_suppkey = s.s_suppkey) ON ps.ps_suppkey = l.l_suppkey) ON o.o_orderkey = l.l_orderkey)
WHERE p.p_name LIKE '%green%'
GROUP BY p.p_partkey;
