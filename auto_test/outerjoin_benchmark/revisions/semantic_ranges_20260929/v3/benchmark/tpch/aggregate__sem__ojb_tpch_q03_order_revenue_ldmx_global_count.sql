-- source: TPC-H Q3
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: TPC-H Q3 orders booked before a reporting deadline
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=o.o_custkey; group_key=c.c_custkey
-- semantic_filter: tpch_order_deadline; tier=low; TPC-H Q3 orders booked before a reporting deadline
-- predicate: o.o_orderdate < DATE '1992-03-15'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM ((customer c LEFT OUTER JOIN orders o ON c.c_custkey = o.o_custkey) RIGHT OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey)
WHERE o.o_orderdate < DATE '1992-03-15';
