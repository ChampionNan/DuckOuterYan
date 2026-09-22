-- source: TPC-DS Q51
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: Web and store sales streams are reconciled by item and date coverage.
-- corpus_revision: v1-mixed-20260922
SELECT *
FROM (date_dim d LEFT OUTER JOIN (web_sales ws RIGHT OUTER JOIN store_sales ss ON ws.ws_item_sk = ss.ss_item_sk) ON ws.ws_sold_date_sk = d.d_date_sk)
WHERE ws.ws_order_number % 1000 = 0;
