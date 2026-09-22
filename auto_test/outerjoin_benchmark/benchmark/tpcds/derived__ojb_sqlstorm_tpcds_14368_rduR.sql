-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_revision: v1-mixed-20260922
SELECT *
FROM (customer_address ca INNER JOIN (customer c LEFT OUTER JOIN (item i RIGHT OUTER JOIN (date_dim d FULL OUTER JOIN (web_sales ws INNER JOIN ship_mode sm ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk) ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_item_sk = i.i_item_sk) ON c.c_customer_sk = ws.ws_bill_customer_sk) ON c.c_current_addr_sk = ca.ca_address_sk)
WHERE c.c_customer_sk % 1000 = 0;
