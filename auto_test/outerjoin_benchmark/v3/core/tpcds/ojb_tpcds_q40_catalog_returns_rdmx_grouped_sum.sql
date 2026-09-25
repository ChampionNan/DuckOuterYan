-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Catalog return attribution: every qualifying catalog sale remains visible even when no matching return exists; dimensions enrich it.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=cs.cs_order_number; group_key=cr.cr_order_number
SELECT cr.cr_order_number AS group_key, SUM(cs.cs_order_number) AS key_sum
FROM (date_dim d INNER JOIN (item i FULL OUTER JOIN (warehouse w RIGHT OUTER JOIN (catalog_returns cr LEFT OUTER JOIN catalog_sales cs ON cs.cs_order_number = cr.cr_order_number) ON cs.cs_warehouse_sk = w.w_warehouse_sk) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE cs.cs_order_number % 1000 = 0
GROUP BY cr.cr_order_number;
