-- source: TPC-DS Q80
-- transformation: connected join-subgraph adaptation; balanced mixed secondary right-deep source-derived form
-- business_semantics: Store sales retain optional return records and date, store, and item annotations.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=ss.ss_item_sk; predicate=hash(anchor) % 20 = 0
SELECT *
FROM (item i LEFT OUTER JOIN (store s INNER JOIN (store_returns sr RIGHT OUTER JOIN (store_sales ss FULL OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_item_sk = sr.sr_item_sk) ON ss.ss_store_sk = s.s_store_sk) ON ss.ss_item_sk = i.i_item_sk)
WHERE (ss.ss_ticket_number % 1000 = 0)
  AND hash(ss.ss_item_sk) % 20 = 0;
