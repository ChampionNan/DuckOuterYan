-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- transformation: connected join-subgraph adaptation; cross-product-free bushy FULL-outer applicability form
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress02; approximately 0.2% of hash buckets; anchor=C.c_customer_sk; predicate=hash(C.c_customer_sk) % 4000 < 8
SELECT *
FROM (((customer C FULL OUTER JOIN customer_demographics CD ON C.c_current_cdemo_sk = CD.cd_demo_sk) FULL OUTER JOIN customer_address CA ON C.c_current_addr_sk = CA.ca_address_sk) FULL OUTER JOIN ((web_sales WS FULL OUTER JOIN date_dim D ON WS.ws_sold_date_sk = D.d_date_sk) FULL OUTER JOIN item I ON WS.ws_item_sk = I.i_item_sk) ON C.c_customer_sk = WS.ws_bill_customer_sk)
WHERE hash(C.c_customer_sk) % 4000 < 8;
