-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-DS Q5
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM (((web_returns wr FULL OUTER JOIN web_sales ws ON wr.wr_item_sk = ws.ws_item_sk AND wr.wr_order_number = ws.ws_order_number) RIGHT OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) LEFT OUTER JOIN web_site web ON ws.ws_web_site_sk = web.web_site_sk)
WHERE d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19';
