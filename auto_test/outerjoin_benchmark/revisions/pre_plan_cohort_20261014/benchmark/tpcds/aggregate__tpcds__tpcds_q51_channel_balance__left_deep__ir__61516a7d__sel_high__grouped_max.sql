-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-DS Q51
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT d.d_date_sk AS group_key, MAX(ws.ws_sold_date_sk) AS max_key
FROM ((date_dim d INNER JOIN web_sales ws ON ws.ws_sold_date_sk = d.d_date_sk) RIGHT OUTER JOIN store_sales ss ON ws.ws_item_sk = ss.ss_item_sk AND ws.ws_sold_date_sk = ss.ss_sold_date_sk)
WHERE d.d_date BETWEEN DATE '1999-05-08' AND DATE '2001-12-23'
GROUP BY d.d_date_sk;
