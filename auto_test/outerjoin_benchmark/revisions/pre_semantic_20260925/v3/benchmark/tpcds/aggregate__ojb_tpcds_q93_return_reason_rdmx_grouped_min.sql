-- source: TPC-DS Q93
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Store-sale records are associated with optional returns and their reason dimension.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_min; anchor=sr.sr_item_sk; group_key=ss.ss_item_sk
SELECT ss.ss_item_sk AS group_key, MIN(sr.sr_item_sk) AS min_key
FROM (reason r LEFT OUTER JOIN (store_returns sr INNER JOIN store_sales ss ON ss.ss_item_sk = sr.sr_item_sk) ON sr.sr_reason_sk = r.r_reason_sk)
WHERE ss.ss_ticket_number % 1000 = 0
GROUP BY ss.ss_item_sk;
