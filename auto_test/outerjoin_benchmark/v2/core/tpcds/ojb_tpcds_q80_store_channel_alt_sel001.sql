-- source: TPC-DS Q80
-- transformation: connected join-subgraph adaptation; alternate mixed form; bushy grouping is structurally ineligible
-- business_semantics: Store sales retain optional return records and date, store, and item annotations.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=ss.ss_item_sk; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM ((((store_sales ss FULL OUTER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk) RIGHT OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) INNER JOIN store s ON ss.ss_store_sk = s.s_store_sk) LEFT OUTER JOIN item i ON ss.ss_item_sk = i.i_item_sk)
WHERE (ss.ss_ticket_number % 1000 = 0)
  AND hash(ss.ss_item_sk) % 1000 = 0;
