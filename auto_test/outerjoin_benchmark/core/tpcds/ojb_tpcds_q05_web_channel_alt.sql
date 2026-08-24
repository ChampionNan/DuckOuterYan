-- source: TPC-DS Q5
-- transformation: connected join-subgraph adaptation; alternate mixed form; bushy grouping is structurally ineligible
-- business_semantics: Web returns are reconciled with sales and enriched with date and site context.
SELECT *
FROM (((web_returns wr LEFT OUTER JOIN web_sales ws ON wr.wr_item_sk = ws.ws_item_sk) FULL OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) RIGHT OUTER JOIN web_site web ON ws.ws_web_site_sk = web.web_site_sk)
WHERE wr.wr_order_number % 1000 = 0;
