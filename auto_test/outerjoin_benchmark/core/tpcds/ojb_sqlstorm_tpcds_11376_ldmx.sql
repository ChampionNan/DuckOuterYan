-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- transformation: connected join-subgraph adaptation; primary left-deep mixed join labeling
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM ((((customer c LEFT OUTER JOIN store_sales ss ON c.c_customer_sk = ss.ss_customer_sk) FULL OUTER JOIN item i ON ss.ss_item_sk = i.i_item_sk) RIGHT OUTER JOIN web_sales ws ON i.i_item_sk = ws.ws_item_sk) INNER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk)
WHERE (c.c_customer_sk % 1000 = 0 OR c.c_customer_sk IS NULL);
