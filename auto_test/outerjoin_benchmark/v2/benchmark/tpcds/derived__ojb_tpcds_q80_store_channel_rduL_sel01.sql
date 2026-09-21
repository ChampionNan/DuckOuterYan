-- source: TPC-DS Q80
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: Store sales retain optional return records and date, store, and item annotations.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=ss.ss_item_sk; predicate=hash(anchor) % 100 = 0
SELECT *
FROM (store_returns sr FULL OUTER JOIN (date_dim d FULL OUTER JOIN (store s FULL OUTER JOIN (store_sales ss FULL OUTER JOIN item i ON ss.ss_item_sk = i.i_item_sk) ON ss.ss_store_sk = s.s_store_sk) ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_item_sk = sr.sr_item_sk)
WHERE (ss.ss_ticket_number % 1000 = 0)
  AND hash(ss.ss_item_sk) % 100 = 0;
