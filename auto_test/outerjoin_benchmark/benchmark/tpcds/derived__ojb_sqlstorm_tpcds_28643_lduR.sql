-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- transformation: connected join-subgraph adaptation; uniform left-deep RIGHT OUTER JOIN control
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (((((customer C RIGHT OUTER JOIN customer_address CA ON C.c_current_addr_sk = CA.ca_address_sk) RIGHT OUTER JOIN customer_demographics CD ON C.c_current_cdemo_sk = CD.cd_demo_sk) RIGHT OUTER JOIN web_sales WS ON C.c_customer_sk = WS.ws_bill_customer_sk) RIGHT OUTER JOIN item I ON WS.ws_item_sk = I.i_item_sk) RIGHT OUTER JOIN date_dim D ON WS.ws_sold_date_sk = D.d_date_sk)
WHERE C.c_customer_sk % 1000 = 0;
