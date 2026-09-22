-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_revision: v1-mixed-20260922
SELECT *
FROM ((web_sales ws INNER JOIN item i ON i.i_item_sk = ws.ws_item_sk) FULL OUTER JOIN ((store_sales ss RIGHT OUTER JOIN customer c ON c.c_customer_sk = ss.ss_customer_sk) LEFT OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_item_sk = i.i_item_sk)
WHERE c.c_customer_sk % 1000 = 0;
