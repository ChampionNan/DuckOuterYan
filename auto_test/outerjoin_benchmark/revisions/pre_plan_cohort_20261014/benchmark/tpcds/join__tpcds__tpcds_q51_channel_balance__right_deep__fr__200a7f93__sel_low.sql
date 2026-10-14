-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-DS Q51
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ws.ws_sold_date_sk, d.d_date_sk, ws.ws_item_sk, ss.ss_item_sk, ss.ss_sold_date_sk
FROM (store_sales ss FULL OUTER JOIN (web_sales ws RIGHT OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_item_sk = ss.ss_item_sk AND ws.ws_sold_date_sk = ss.ss_sold_date_sk)
WHERE d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19';
