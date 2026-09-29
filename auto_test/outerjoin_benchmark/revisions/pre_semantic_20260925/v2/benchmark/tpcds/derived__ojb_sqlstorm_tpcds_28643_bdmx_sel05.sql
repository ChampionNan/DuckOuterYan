-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=WS.ws_bill_customer_sk; predicate=hash(anchor) % 20 = 0
SELECT *
FROM (((item I LEFT OUTER JOIN web_sales WS ON WS.ws_item_sk = I.i_item_sk) RIGHT OUTER JOIN date_dim D ON WS.ws_sold_date_sk = D.d_date_sk) INNER JOIN ((customer_address CA RIGHT OUTER JOIN customer C ON C.c_current_addr_sk = CA.ca_address_sk) FULL OUTER JOIN customer_demographics CD ON C.c_current_cdemo_sk = CD.cd_demo_sk) ON C.c_customer_sk = WS.ws_bill_customer_sk)
WHERE (C.c_customer_sk % 1000 = 0)
  AND hash(WS.ws_bill_customer_sk) % 20 = 0;
