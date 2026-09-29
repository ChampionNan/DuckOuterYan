-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_max; anchor=ws.ws_bill_customer_sk; group_key=c.c_current_addr_sk
SELECT c.c_current_addr_sk AS group_key, MAX(ws.ws_bill_customer_sk) AS max_key
FROM ((customer c RIGHT OUTER JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk) FULL OUTER JOIN (((web_sales ws RIGHT OUTER JOIN ship_mode sm ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk) LEFT OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) INNER JOIN item i ON ws.ws_item_sk = i.i_item_sk) ON c.c_customer_sk = ws.ws_bill_customer_sk)
WHERE c.c_customer_sk % 1000 = 0
GROUP BY c.c_current_addr_sk;
