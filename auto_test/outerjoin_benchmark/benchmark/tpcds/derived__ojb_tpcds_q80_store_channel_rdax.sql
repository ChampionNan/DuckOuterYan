-- source: TPC-DS Q80
-- transformation: connected join-subgraph adaptation; balanced mixed secondary right-deep source-derived form
-- business_semantics: Store sales retain optional return records and date, store, and item annotations.
-- corpus_revision: v1-mixed-20260922
SELECT *
FROM (item i LEFT OUTER JOIN (store s INNER JOIN (store_returns sr RIGHT OUTER JOIN (store_sales ss FULL OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_item_sk = sr.sr_item_sk) ON ss.ss_store_sk = s.s_store_sk) ON ss.ss_item_sk = i.i_item_sk)
WHERE ss.ss_ticket_number % 1000 = 0;
