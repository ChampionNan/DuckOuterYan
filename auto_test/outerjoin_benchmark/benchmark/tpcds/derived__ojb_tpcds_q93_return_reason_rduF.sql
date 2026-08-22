-- source: TPC-DS Q93
-- transformation: connected join-subgraph adaptation; uniform right-deep FULL OUTER JOIN control
-- business_semantics: Store-sale records are associated with optional returns and their reason dimension.
SELECT *
FROM (reason r FULL OUTER JOIN (store_returns sr FULL OUTER JOIN store_sales ss ON ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number) ON sr.sr_reason_sk = r.r_reason_sk)
WHERE ss.ss_ticket_number % 1000 = 0;
