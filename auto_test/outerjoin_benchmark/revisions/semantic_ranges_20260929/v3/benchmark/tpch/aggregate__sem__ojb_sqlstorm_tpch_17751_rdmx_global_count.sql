-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: SQLStorm 17751 shipment reporting period
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=ps.ps_partkey; group_key=p.p_partkey
-- semantic_filter: sqlstorm_shipment_period; tier=low; SQLStorm 17751 shipment reporting period
-- predicate: l.l_shipdate BETWEEN DATE '1997-01-01' AND DATE '1997-03-15'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM (lineitem l INNER JOIN (supplier s FULL OUTER JOIN (partsupp ps RIGHT OUTER JOIN part p ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = l.l_partkey)
WHERE l.l_shipdate BETWEEN DATE '1997-01-01' AND DATE '1997-03-15';
