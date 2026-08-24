-- source: TPC-DS Q5
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: Web returns are reconciled with sales and enriched with date and site context.
SELECT *
FROM (((web_site web FULL OUTER JOIN web_sales ws ON ws.ws_web_site_sk = web.web_site_sk) FULL OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) FULL OUTER JOIN web_returns wr ON wr.wr_item_sk = ws.ws_item_sk)
WHERE wr.wr_order_number % 1000 = 0;
