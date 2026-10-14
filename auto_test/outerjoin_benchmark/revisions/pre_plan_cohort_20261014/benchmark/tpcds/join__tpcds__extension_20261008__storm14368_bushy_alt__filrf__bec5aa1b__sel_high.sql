-- corpus_revision: balanced-screened-20261002; component: tpcds-selectivity-extension-20261008
-- historical_pattern: derived__ojb_sqlstorm_tpcds_14368_bdmx_sel05
-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- selectivity: high; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=preserve_select_star
SELECT *
FROM ((((item i LEFT OUTER JOIN web_sales ws ON ws.ws_item_sk = i.i_item_sk) FULL OUTER JOIN ship_mode sm ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk) RIGHT OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) INNER JOIN (customer_address ca FULL OUTER JOIN customer c ON c.c_current_addr_sk = ca.ca_address_sk) ON c.c_customer_sk = ws.ws_bill_customer_sk)
WHERE (c.c_customer_sk % 100) < 55;
