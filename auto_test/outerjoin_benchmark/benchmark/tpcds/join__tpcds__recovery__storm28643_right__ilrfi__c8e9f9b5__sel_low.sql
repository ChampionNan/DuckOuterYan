-- corpus_revision: balanced-screened-20261002; component: tpcds-recovery-20261005
-- historical_pattern: derived__ojb_sqlstorm_tpcds_28643_rdmx
-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- selectivity: low; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=archive_projection
SELECT *
FROM (date_dim D INNER JOIN (item I FULL OUTER JOIN (web_sales WS RIGHT OUTER JOIN (customer_demographics CD LEFT OUTER JOIN (customer_address CA INNER JOIN customer C ON C.c_current_addr_sk = CA.ca_address_sk) ON C.c_current_cdemo_sk = CD.cd_demo_sk) ON C.c_customer_sk = WS.ws_bill_customer_sk) ON WS.ws_item_sk = I.i_item_sk) ON WS.ws_sold_date_sk = D.d_date_sk)
WHERE (C.c_customer_sk % 100) < 3;
