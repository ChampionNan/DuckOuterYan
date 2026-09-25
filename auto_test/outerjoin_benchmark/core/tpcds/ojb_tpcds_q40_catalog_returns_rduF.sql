-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: Catalog return attribution: every qualifying catalog sale remains visible even when no matching return exists; dimensions enrich it.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, w.w_state, i.i_item_id, d.d_date
FROM (catalog_returns cr INNER JOIN (warehouse w LEFT OUTER JOIN (item i RIGHT OUTER JOIN (catalog_sales cs FULL OUTER JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_warehouse_sk = w.w_warehouse_sk) ON cs.cs_order_number = cr.cr_order_number)
WHERE cs.cs_order_number % 1000 = 0;
