-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: catalog sales reporting period
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=cs.cs_order_number; group_key=cr.cr_order_number
-- semantic_filter: tpcds_catalog_date; tier=low; catalog sales reporting period
-- predicate: d.d_date BETWEEN DATE '2000-01-25' AND DATE '2000-04-26'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT cr.cr_order_number AS group_key, SUM(cs.cs_order_number) AS key_sum
FROM (date_dim d INNER JOIN (item i FULL OUTER JOIN (warehouse w RIGHT OUTER JOIN (catalog_returns cr LEFT OUTER JOIN catalog_sales cs ON cs.cs_order_number = cr.cr_order_number) ON cs.cs_warehouse_sk = w.w_warehouse_sk) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE d.d_date BETWEEN DATE '2000-01-25' AND DATE '2000-04-26'
GROUP BY cr.cr_order_number;
