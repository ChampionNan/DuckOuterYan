-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT C.c_current_addr_sk, CA.ca_address_sk, C.c_current_cdemo_sk, CD.cd_demo_sk, C.c_customer_sk, WS.ws_bill_customer_sk, WS.ws_item_sk, I.i_item_sk, WS.ws_sold_date_sk, D.d_date_sk
FROM (((customer C INNER JOIN customer_address CA ON C.c_current_addr_sk = CA.ca_address_sk) LEFT OUTER JOIN customer_demographics CD ON C.c_current_cdemo_sk = CD.cd_demo_sk) RIGHT OUTER JOIN (date_dim D INNER JOIN (item I FULL OUTER JOIN web_sales WS ON WS.ws_item_sk = I.i_item_sk) ON WS.ws_sold_date_sk = D.d_date_sk) ON C.c_customer_sk = WS.ws_bill_customer_sk)
WHERE D.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19';
