-- source: TPC-DS Q5
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: Web returns are reconciled with sales and enriched with date and site context.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=ws.ws_item_sk; predicate=hash(anchor) % 20 = 0
SELECT *
FROM (web_returns wr FULL OUTER JOIN (date_dim d FULL OUTER JOIN (web_sales ws FULL OUTER JOIN web_site web ON ws.ws_web_site_sk = web.web_site_sk) ON ws.ws_sold_date_sk = d.d_date_sk) ON wr.wr_item_sk = ws.ws_item_sk)
WHERE (wr.wr_order_number % 1000 = 0)
  AND hash(ws.ws_item_sk) % 20 = 0;
