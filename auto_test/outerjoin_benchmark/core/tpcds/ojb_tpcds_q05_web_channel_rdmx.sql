-- source: TPC-DS Q5
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: Web returns are reconciled with sales and enriched with date and site context.
SELECT *
FROM (web_site web FULL OUTER JOIN (date_dim d RIGHT OUTER JOIN (web_sales ws INNER JOIN web_returns wr ON wr.wr_item_sk = ws.ws_item_sk AND wr.wr_order_number = ws.ws_order_number) ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_web_site_sk = web.web_site_sk)
WHERE (wr.wr_order_number % 1000 = 0 OR wr.wr_order_number IS NULL);
