-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-DS Q51
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ws.ws_sold_date_sk, d.d_date_sk, ws.ws_item_sk, ss.ss_item_sk, ss.ss_sold_date_sk
FROM ((date_dim d RIGHT OUTER JOIN web_sales ws ON ws.ws_sold_date_sk = d.d_date_sk) LEFT OUTER JOIN store_sales ss ON ws.ws_item_sk = ss.ss_item_sk AND ws.ws_sold_date_sk = ss.ss_sold_date_sk)
WHERE d.d_date BETWEEN DATE '1999-11-18' AND DATE '2001-06-12';
