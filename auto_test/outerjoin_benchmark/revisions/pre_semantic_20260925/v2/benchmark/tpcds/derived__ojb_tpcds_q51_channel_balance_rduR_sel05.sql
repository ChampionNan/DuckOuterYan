-- source: TPC-DS Q51
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: Web and store sales streams are reconciled by item and date coverage.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=ws.ws_sold_date_sk; predicate=hash(anchor) % 20 = 0
SELECT *
FROM (date_dim d LEFT OUTER JOIN (web_sales ws RIGHT OUTER JOIN store_sales ss ON ws.ws_item_sk = ss.ss_item_sk) ON ws.ws_sold_date_sk = d.d_date_sk)
WHERE (ws.ws_order_number % 1000 = 0)
  AND hash(ws.ws_sold_date_sk) % 20 = 0;
