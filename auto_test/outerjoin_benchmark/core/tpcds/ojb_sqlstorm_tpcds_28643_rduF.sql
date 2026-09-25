-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM (customer_address CA FULL OUTER JOIN (customer_demographics CD INNER JOIN (customer C LEFT OUTER JOIN (item I RIGHT OUTER JOIN (web_sales WS FULL OUTER JOIN date_dim D ON WS.ws_sold_date_sk = D.d_date_sk) ON WS.ws_item_sk = I.i_item_sk) ON C.c_customer_sk = WS.ws_bill_customer_sk) ON C.c_current_cdemo_sk = CD.cd_demo_sk) ON C.c_current_addr_sk = CA.ca_address_sk)
WHERE C.c_customer_sk % 1000 = 0;
