-- source: TPC-DS Q51
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: Web and store sales streams are reconciled by item and date coverage.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=ws.ws_sold_date_sk; predicate=hash(anchor) % 100 = 0
SELECT *
FROM ((web_sales ws FULL OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) INNER JOIN store_sales ss ON ws.ws_item_sk = ss.ss_item_sk)
WHERE (ws.ws_order_number % 1000 = 0)
  AND hash(ws.ws_sold_date_sk) % 100 = 0;
