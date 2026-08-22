-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: Catalog return attribution: every qualifying catalog sale remains visible even when no matching return exists; dimensions enrich it.
SELECT cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, w.w_state, i.i_item_id, d.d_date
FROM (date_dim d INNER JOIN (item i INNER JOIN (warehouse w INNER JOIN (catalog_returns cr RIGHT OUTER JOIN catalog_sales cs ON cs.cs_order_number = cr.cr_order_number AND cs.cs_item_sk = cr.cr_item_sk) ON cs.cs_warehouse_sk = w.w_warehouse_sk) ON cs.cs_item_sk = i.i_item_sk AND i.i_current_price BETWEEN 0.99 AND 1.49) ON cs.cs_sold_date_sk = d.d_date_sk AND d.d_date BETWEEN DATE '2000-02-10' AND DATE '2000-04-10')
WHERE cs.cs_order_number % 1000 = 0;
