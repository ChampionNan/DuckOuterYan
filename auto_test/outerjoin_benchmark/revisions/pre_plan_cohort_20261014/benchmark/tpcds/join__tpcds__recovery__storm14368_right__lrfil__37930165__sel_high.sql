-- corpus_revision: balanced-screened-20261002; component: tpcds-recovery-20261005
-- historical_pattern: derived__ojb_sqlstorm_tpcds_14368_rdmx
-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- selectivity: high; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=archive_projection
SELECT *
FROM (ship_mode sm LEFT OUTER JOIN (date_dim d INNER JOIN (item i FULL OUTER JOIN (web_sales ws RIGHT OUTER JOIN (customer_address ca LEFT OUTER JOIN customer c ON c.c_current_addr_sk = ca.ca_address_sk) ON c.c_customer_sk = ws.ws_bill_customer_sk) ON ws.ws_item_sk = i.i_item_sk) ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk)
WHERE (c.c_customer_sk % 100) < 55;
