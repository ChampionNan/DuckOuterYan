-- source: TPC-DS Q51
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: Web and store sales streams are reconciled by item and date coverage.
-- corpus_revision: v1-mixed-20260922
SELECT *
FROM ((web_sales ws FULL OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) INNER JOIN store_sales ss ON ws.ws_item_sk = ss.ss_item_sk)
WHERE ws.ws_order_number % 1000 = 0;
