-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress10; approximately 10% of hash buckets; anchor=c.c_customer_sk; predicate=hash(c.c_customer_sk) % 4000 < 400
SELECT *
FROM (customer_address ca FULL OUTER JOIN (customer c FULL OUTER JOIN (item i FULL OUTER JOIN (date_dim d FULL OUTER JOIN (web_sales ws FULL OUTER JOIN ship_mode sm ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk) ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_item_sk = i.i_item_sk) ON c.c_customer_sk = ws.ws_bill_customer_sk) ON c.c_current_addr_sk = ca.ca_address_sk)
WHERE hash(c.c_customer_sk) % 4000 < 400;
