-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Catalog return attribution: every qualifying catalog sale remains visible even when no matching return exists; dimensions enrich it.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=cs.cs_order_number; group_key=cr.cr_order_number
SELECT COUNT(*) AS row_count
FROM ((((catalog_sales cs INNER JOIN catalog_returns cr ON cs.cs_order_number = cr.cr_order_number) LEFT OUTER JOIN warehouse w ON cs.cs_warehouse_sk = w.w_warehouse_sk) RIGHT OUTER JOIN item i ON cs.cs_item_sk = i.i_item_sk) FULL OUTER JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE cs.cs_order_number % 1000 = 0;
