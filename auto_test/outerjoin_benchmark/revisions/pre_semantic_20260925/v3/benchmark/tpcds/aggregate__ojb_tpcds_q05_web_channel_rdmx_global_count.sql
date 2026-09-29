-- source: TPC-DS Q5
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Web returns are reconciled with sales and enriched with date and site context.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=ws.ws_item_sk; group_key=wr.wr_item_sk
SELECT COUNT(*) AS row_count
FROM (web_site web FULL OUTER JOIN (date_dim d RIGHT OUTER JOIN (web_sales ws LEFT OUTER JOIN web_returns wr ON wr.wr_item_sk = ws.ws_item_sk) ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_web_site_sk = web.web_site_sk)
WHERE wr.wr_order_number % 1000 = 0;
