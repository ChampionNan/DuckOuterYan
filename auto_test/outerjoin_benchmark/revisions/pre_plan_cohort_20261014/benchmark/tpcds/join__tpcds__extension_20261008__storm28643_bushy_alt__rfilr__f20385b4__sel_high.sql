-- corpus_revision: balanced-screened-20261002; component: tpcds-selectivity-extension-20261008
-- historical_pattern: derived__ojb_sqlstorm_tpcds_28643_bdmx_sel001
-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- selectivity: high; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=preserve_select_star
SELECT *
FROM (((item I LEFT OUTER JOIN web_sales WS ON WS.ws_item_sk = I.i_item_sk) RIGHT OUTER JOIN date_dim D ON WS.ws_sold_date_sk = D.d_date_sk) INNER JOIN ((customer_address CA RIGHT OUTER JOIN customer C ON C.c_current_addr_sk = CA.ca_address_sk) FULL OUTER JOIN customer_demographics CD ON C.c_current_cdemo_sk = CD.cd_demo_sk) ON C.c_customer_sk = WS.ws_bill_customer_sk)
WHERE (C.c_customer_sk % 100) < 55;
