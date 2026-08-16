-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; uniform left-deep RIGHT OUTER JOIN control
-- business_semantics: Catalog return attribution: every qualifying catalog sale remains visible even when no matching return exists; dimensions enrich it.
SELECT cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, w.w_state, i.i_item_id, d.d_date
FROM ((((catalog_sales cs RIGHT OUTER JOIN catalog_returns cr ON cs.cs_order_number = cr.cr_order_number AND cs.cs_item_sk = cr.cr_item_sk) RIGHT OUTER JOIN warehouse w ON cs.cs_warehouse_sk = w.w_warehouse_sk) RIGHT OUTER JOIN item i ON cs.cs_item_sk = i.i_item_sk AND i.i_current_price BETWEEN 0.99 AND 1.49) RIGHT OUTER JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk AND d.d_date BETWEEN DATE '2000-02-10' AND DATE '2000-04-10')
WHERE (cs.cs_order_number % 1000 = 0 OR cs.cs_order_number IS NULL);
