-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT c.c_customer_sk, ss.ss_customer_sk, ss.ss_item_sk, i.i_item_sk, ws.ws_item_sk, ss.ss_sold_date_sk, d.d_date_sk
FROM (date_dim d FULL OUTER JOIN (web_sales ws INNER JOIN (item i LEFT OUTER JOIN (store_sales ss RIGHT OUTER JOIN customer c ON c.c_customer_sk = ss.ss_customer_sk) ON ss.ss_item_sk = i.i_item_sk) ON i.i_item_sk = ws.ws_item_sk) ON ss.ss_sold_date_sk = d.d_date_sk)
WHERE d.d_date BETWEEN DATE '2000-08-09' AND DATE '2000-09-20';
