-- corpus_revision: balanced-screened-20261002; component: tpcds-selectivity-extension-20261008
-- historical_pattern: derived__ojb_sqlstorm_tpcds_11376_ldmx_sel01
-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- selectivity: high; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=preserve_select_star
SELECT *
FROM ((((customer c FULL OUTER JOIN store_sales ss ON c.c_customer_sk = ss.ss_customer_sk) INNER JOIN item i ON ss.ss_item_sk = i.i_item_sk) LEFT OUTER JOIN web_sales ws ON i.i_item_sk = ws.ws_item_sk) RIGHT OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk)
WHERE (c.c_customer_sk % 100) < 55;
