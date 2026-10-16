-- corpus_revision: balanced-screened-20261002; component: tpcds-recovery-20261005
-- historical_pattern: derived__ojb_tpcds_q40_catalog_returns_rdmx_sel01
-- source: TPC-DS Q40
-- selectivity: low; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=global_count
SELECT COUNT(*) AS row_count
FROM (date_dim d INNER JOIN (item i FULL OUTER JOIN (warehouse w RIGHT OUTER JOIN (catalog_returns cr LEFT OUTER JOIN catalog_sales cs ON cs.cs_order_number = cr.cr_order_number) ON cs.cs_warehouse_sk = w.w_warehouse_sk) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE (cs.cs_order_number % 100) < 3;
