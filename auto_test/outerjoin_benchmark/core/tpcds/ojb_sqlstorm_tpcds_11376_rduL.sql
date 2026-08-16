-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- transformation: connected join-subgraph adaptation; uniform right-deep LEFT OUTER JOIN control
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (date_dim d LEFT OUTER JOIN (web_sales ws LEFT OUTER JOIN (item i LEFT OUTER JOIN (store_sales ss LEFT OUTER JOIN customer c ON c.c_customer_sk = ss.ss_customer_sk) ON ss.ss_item_sk = i.i_item_sk) ON i.i_item_sk = ws.ws_item_sk) ON ss.ss_sold_date_sk = d.d_date_sk)
WHERE (c.c_customer_sk % 1000 = 0 OR c.c_customer_sk IS NULL);
