-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT c.c_customer_sk, ss.ss_customer_sk, ss.ss_item_sk, i.i_item_sk, ws.ws_item_sk, ss.ss_sold_date_sk, d.d_date_sk
FROM (((customer c RIGHT OUTER JOIN store_sales ss ON c.c_customer_sk = ss.ss_customer_sk) INNER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) FULL OUTER JOIN (web_sales ws LEFT OUTER JOIN item i ON i.i_item_sk = ws.ws_item_sk) ON ss.ss_item_sk = i.i_item_sk)
WHERE d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24';
