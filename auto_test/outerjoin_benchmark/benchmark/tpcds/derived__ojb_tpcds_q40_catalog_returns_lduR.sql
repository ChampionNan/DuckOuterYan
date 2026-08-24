-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: Catalog return attribution: every qualifying catalog sale remains visible even when no matching return exists; dimensions enrich it.
SELECT cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, w.w_state, i.i_item_id, d.d_date
FROM ((((date_dim d FULL OUTER JOIN catalog_sales cs ON cs.cs_sold_date_sk = d.d_date_sk) FULL OUTER JOIN item i ON cs.cs_item_sk = i.i_item_sk) FULL OUTER JOIN warehouse w ON cs.cs_warehouse_sk = w.w_warehouse_sk) FULL OUTER JOIN catalog_returns cr ON cs.cs_order_number = cr.cr_order_number)
WHERE cs.cs_order_number % 1000 = 0;
