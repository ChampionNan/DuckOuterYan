-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (((((ship_mode sm FULL OUTER JOIN web_sales ws ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk) FULL OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) FULL OUTER JOIN item i ON ws.ws_item_sk = i.i_item_sk) FULL OUTER JOIN customer c ON c.c_customer_sk = ws.ws_bill_customer_sk) FULL OUTER JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk)
WHERE c.c_customer_sk % 1000 = 0;
