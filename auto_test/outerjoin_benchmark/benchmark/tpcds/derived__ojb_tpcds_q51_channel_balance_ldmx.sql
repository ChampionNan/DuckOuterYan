-- source: TPC-DS Q51
-- transformation: connected join-subgraph adaptation; primary left-deep mixed join labeling
-- business_semantics: Web and store sales streams are reconciled by item and date coverage.
SELECT *
FROM ((web_sales ws RIGHT OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) INNER JOIN store_sales ss ON ws.ws_item_sk = ss.ss_item_sk AND ws.ws_sold_date_sk = ss.ss_sold_date_sk)
WHERE ws.ws_order_number % 1000 = 0;
