-- source: TPC-DS Q93
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: Store-sale records are associated with optional returns and their reason dimension.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=sr.sr_item_sk; predicate=hash(anchor) % 100 = 0
SELECT *
FROM (store_sales ss FULL OUTER JOIN (store_returns sr INNER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk) ON ss.ss_item_sk = sr.sr_item_sk)
WHERE (ss.ss_ticket_number % 1000 = 0)
  AND hash(sr.sr_item_sk) % 100 = 0;
