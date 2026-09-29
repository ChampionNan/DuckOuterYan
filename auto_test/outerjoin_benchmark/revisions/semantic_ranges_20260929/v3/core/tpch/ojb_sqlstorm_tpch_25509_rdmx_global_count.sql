-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: SQLStorm 25509 order reporting period
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=o.o_orderkey; group_key=p.p_partkey
-- semantic_filter: sqlstorm_order_period; tier=medium; SQLStorm 25509 order reporting period
-- predicate: o.o_orderdate BETWEEN DATE '1996-01-01' AND DATE '1996-12-31'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM (customer c LEFT OUTER JOIN (orders o INNER JOIN (lineitem l FULL OUTER JOIN (supplier s RIGHT OUTER JOIN (partsupp ps LEFT OUTER JOIN part p ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = l.l_partkey) ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey)
WHERE o.o_orderdate BETWEEN DATE '1996-01-01' AND DATE '1996-12-31';
