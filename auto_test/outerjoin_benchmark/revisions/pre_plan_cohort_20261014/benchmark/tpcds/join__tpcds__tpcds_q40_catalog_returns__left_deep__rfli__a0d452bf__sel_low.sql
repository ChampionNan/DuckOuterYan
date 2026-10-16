-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-DS Q40
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, w.w_state, i.i_item_id, d.d_date
FROM ((((catalog_sales cs RIGHT OUTER JOIN catalog_returns cr ON cs.cs_order_number = cr.cr_order_number AND cs.cs_item_sk = cr.cr_item_sk) FULL OUTER JOIN warehouse w ON cs.cs_warehouse_sk = w.w_warehouse_sk) LEFT OUTER JOIN item i ON cs.cs_item_sk = i.i_item_sk) INNER JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE d.d_date BETWEEN DATE '2000-01-25' AND DATE '2000-04-26';
