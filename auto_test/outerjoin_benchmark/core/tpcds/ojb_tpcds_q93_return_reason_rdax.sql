-- source: TPC-DS Q93
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer applicability form
-- business_semantics: Store-sale records are associated with optional returns and their reason dimension.
SELECT *
FROM (reason r FULL OUTER JOIN (store_sales ss FULL OUTER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk) ON sr.sr_reason_sk = r.r_reason_sk)
WHERE ss.ss_ticket_number % 1000 = 0;
