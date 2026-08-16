-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (date_dim D FULL OUTER JOIN (item I RIGHT OUTER JOIN (web_sales WS INNER JOIN (customer_demographics CD LEFT OUTER JOIN (customer_address CA FULL OUTER JOIN customer C ON C.c_current_addr_sk = CA.ca_address_sk) ON C.c_current_cdemo_sk = CD.cd_demo_sk) ON C.c_customer_sk = WS.ws_bill_customer_sk) ON WS.ws_item_sk = I.i_item_sk) ON WS.ws_sold_date_sk = D.d_date_sk)
WHERE (C.c_customer_sk % 1000 = 0 OR C.c_customer_sk IS NULL);
