-- source: TPC-DS Q93
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Store-sale records are associated with optional returns and their reason dimension.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM ((store_sales ss FULL OUTER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk) INNER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk)
WHERE ss.ss_ticket_number % 1000 = 0;
