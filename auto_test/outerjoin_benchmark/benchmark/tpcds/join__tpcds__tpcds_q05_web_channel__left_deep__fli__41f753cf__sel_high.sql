-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-DS Q5
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT wr.wr_item_sk, ws.ws_item_sk, wr.wr_order_number, ws.ws_order_number, ws.ws_sold_date_sk, d.d_date_sk, ws.ws_web_site_sk, web.web_site_sk
FROM (((web_returns wr FULL OUTER JOIN web_sales ws ON wr.wr_item_sk = ws.ws_item_sk AND wr.wr_order_number = ws.ws_order_number) LEFT OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) INNER JOIN web_site web ON ws.ws_web_site_sk = web.web_site_sk)
WHERE d.d_date BETWEEN DATE '1999-05-08' AND DATE '2001-12-23';
