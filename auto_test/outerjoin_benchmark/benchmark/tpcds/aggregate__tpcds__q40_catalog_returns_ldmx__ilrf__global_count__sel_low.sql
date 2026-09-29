-- query_type: aggregate; family: tpcds
-- source: TPC-DS Q40
-- semantic_filter: tpcds_catalog_date; tier=low; catalog sales reporting period
-- predicate: d.d_date BETWEEN DATE '2000-01-25' AND DATE '2000-04-26'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM ((((catalog_sales cs INNER JOIN catalog_returns cr ON cs.cs_order_number = cr.cr_order_number) LEFT OUTER JOIN warehouse w ON cs.cs_warehouse_sk = w.w_warehouse_sk) RIGHT OUTER JOIN item i ON cs.cs_item_sk = i.i_item_sk) FULL OUTER JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE d.d_date BETWEEN DATE '2000-01-25' AND DATE '2000-04-26';
