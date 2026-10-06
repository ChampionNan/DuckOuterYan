-- corpus_revision: balanced-screened-20261002; component: tpcds-recovery-20261005
-- historical_pattern: aggregate__ojb_tpcds_q40_catalog_returns_alt_global_count
-- source: TPC-DS Q40
-- selectivity: high; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=global_count
SELECT COUNT(*) AS row_count
FROM ((((catalog_sales cs RIGHT OUTER JOIN catalog_returns cr ON cs.cs_order_number = cr.cr_order_number) FULL OUTER JOIN warehouse w ON cs.cs_warehouse_sk = w.w_warehouse_sk) INNER JOIN item i ON cs.cs_item_sk = i.i_item_sk) LEFT OUTER JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE (cs.cs_order_number % 100) < 55;
