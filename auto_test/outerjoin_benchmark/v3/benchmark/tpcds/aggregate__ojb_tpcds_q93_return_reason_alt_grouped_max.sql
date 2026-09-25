-- source: TPC-DS Q93
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: Store-sale records are associated with optional returns and their reason dimension.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_max; anchor=sr.sr_item_sk; group_key=ss.ss_item_sk
SELECT ss.ss_item_sk AS group_key, MAX(sr.sr_item_sk) AS max_key
FROM ((store_sales ss LEFT OUTER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk) RIGHT OUTER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk)
WHERE ss.ss_ticket_number % 1000 = 0
GROUP BY ss.ss_item_sk;
