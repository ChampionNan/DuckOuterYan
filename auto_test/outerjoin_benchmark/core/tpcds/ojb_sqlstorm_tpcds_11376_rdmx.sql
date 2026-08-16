-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (date_dim d INNER JOIN (web_sales ws LEFT OUTER JOIN (item i FULL OUTER JOIN (store_sales ss RIGHT OUTER JOIN customer c ON c.c_customer_sk = ss.ss_customer_sk) ON ss.ss_item_sk = i.i_item_sk) ON i.i_item_sk = ws.ws_item_sk) ON ss.ss_sold_date_sk = d.d_date_sk)
WHERE (c.c_customer_sk % 1000 = 0 OR c.c_customer_sk IS NULL);
