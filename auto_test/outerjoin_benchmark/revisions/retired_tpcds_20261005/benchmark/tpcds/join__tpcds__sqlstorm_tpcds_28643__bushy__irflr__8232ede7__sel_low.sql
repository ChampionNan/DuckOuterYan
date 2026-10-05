-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT C.c_current_addr_sk, CA.ca_address_sk, C.c_current_cdemo_sk, CD.cd_demo_sk, C.c_customer_sk, WS.ws_bill_customer_sk, WS.ws_item_sk, I.i_item_sk, WS.ws_sold_date_sk, D.d_date_sk
FROM (((item I INNER JOIN web_sales WS ON WS.ws_item_sk = I.i_item_sk) RIGHT OUTER JOIN date_dim D ON WS.ws_sold_date_sk = D.d_date_sk) FULL OUTER JOIN (customer_demographics CD LEFT OUTER JOIN (customer C RIGHT OUTER JOIN customer_address CA ON C.c_current_addr_sk = CA.ca_address_sk) ON C.c_current_cdemo_sk = CD.cd_demo_sk) ON C.c_customer_sk = WS.ws_bill_customer_sk)
WHERE D.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19';
