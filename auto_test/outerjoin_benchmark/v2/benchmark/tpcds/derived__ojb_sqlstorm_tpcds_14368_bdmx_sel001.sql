-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=ws.ws_bill_customer_sk; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM ((((item i LEFT OUTER JOIN web_sales ws ON ws.ws_item_sk = i.i_item_sk) FULL OUTER JOIN ship_mode sm ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk) RIGHT OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) INNER JOIN (customer_address ca FULL OUTER JOIN customer c ON c.c_current_addr_sk = ca.ca_address_sk) ON c.c_customer_sk = ws.ws_bill_customer_sk)
WHERE (c.c_customer_sk % 1000 = 0)
  AND hash(ws.ws_bill_customer_sk) % 1000 = 0;
