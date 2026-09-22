-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress005; approximately 0.05% of hash buckets; anchor=ws.ws_bill_customer_sk; predicate=hash(ws.ws_bill_customer_sk) % 4000 < 2
SELECT *
FROM (((((customer c INNER JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk) LEFT OUTER JOIN web_sales ws ON c.c_customer_sk = ws.ws_bill_customer_sk) RIGHT OUTER JOIN item i ON ws.ws_item_sk = i.i_item_sk) FULL OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) INNER JOIN ship_mode sm ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk)
WHERE (c.c_customer_sk % 1000 = 0)
  AND hash(ws.ws_bill_customer_sk) % 4000 < 2;
