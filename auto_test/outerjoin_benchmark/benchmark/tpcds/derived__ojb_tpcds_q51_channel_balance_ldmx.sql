-- source: TPC-DS Q51
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: Web and store sales streams are reconciled by item and date coverage.
SELECT *
FROM ((web_sales ws FULL OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) FULL OUTER JOIN store_sales ss ON ws.ws_item_sk = ss.ss_item_sk)
WHERE ws.ws_order_number % 1000 = 0;
