-- source: TPC-DS Q93
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: Store-sale records are associated with optional returns and their reason dimension.
SELECT *
FROM (store_sales ss FULL OUTER JOIN (store_returns sr FULL OUTER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk) ON ss.ss_item_sk = sr.sr_item_sk)
WHERE ss.ss_ticket_number % 1000 = 0;
