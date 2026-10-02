-- query_type: join; family: tpcds
-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- semantic_filter: tpcds_web_date; tier=medium; web sales reporting period
-- predicate: D.d_date BETWEEN DATE '1999-11-18' AND DATE '2001-06-12'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((customer C RIGHT OUTER JOIN customer_demographics CD ON C.c_current_cdemo_sk = CD.cd_demo_sk) LEFT OUTER JOIN customer_address CA ON C.c_current_addr_sk = CA.ca_address_sk) FULL OUTER JOIN ((web_sales WS LEFT OUTER JOIN date_dim D ON WS.ws_sold_date_sk = D.d_date_sk) INNER JOIN item I ON WS.ws_item_sk = I.i_item_sk) ON C.c_customer_sk = WS.ws_bill_customer_sk)
WHERE D.d_date BETWEEN DATE '1999-11-18' AND DATE '2001-06-12';
