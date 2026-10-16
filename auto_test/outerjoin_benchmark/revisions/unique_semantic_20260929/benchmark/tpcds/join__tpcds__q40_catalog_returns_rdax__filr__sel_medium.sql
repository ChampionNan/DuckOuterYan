-- query_type: join; family: tpcds
-- source: TPC-DS Q40
-- semantic_filter: tpcds_catalog_date; tier=medium; catalog sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-06-28' AND DATE '2000-11-23'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, w.w_state, i.i_item_id, d.d_date
FROM (date_dim d RIGHT OUTER JOIN (item i LEFT OUTER JOIN (catalog_returns cr FULL OUTER JOIN (catalog_sales cs INNER JOIN warehouse w ON cs.cs_warehouse_sk = w.w_warehouse_sk) ON cs.cs_order_number = cr.cr_order_number) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE d.d_date BETWEEN DATE '1999-06-28' AND DATE '2000-11-23';
