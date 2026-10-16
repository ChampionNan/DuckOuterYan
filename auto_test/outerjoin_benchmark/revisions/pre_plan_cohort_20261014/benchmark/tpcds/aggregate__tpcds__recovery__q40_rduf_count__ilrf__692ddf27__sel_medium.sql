-- corpus_revision: balanced-screened-20261002; component: tpcds-recovery-20261005
-- historical_pattern: derived__ojb_tpcds_q40_catalog_returns_rduF
-- source: TPC-DS Q40
-- selectivity: medium; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=global_count
SELECT COUNT(*) AS row_count
FROM (catalog_returns cr INNER JOIN (warehouse w LEFT OUTER JOIN (item i RIGHT OUTER JOIN (catalog_sales cs FULL OUTER JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_warehouse_sk = w.w_warehouse_sk) ON cs.cs_order_number = cr.cr_order_number)
WHERE (cs.cs_order_number % 100) < 30;
