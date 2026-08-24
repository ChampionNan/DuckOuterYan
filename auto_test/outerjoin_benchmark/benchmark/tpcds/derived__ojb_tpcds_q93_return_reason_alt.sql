-- source: TPC-DS Q93
-- transformation: connected join-subgraph adaptation; alternate mixed form; bushy grouping is structurally ineligible
-- business_semantics: Store-sale records are associated with optional returns and their reason dimension.
SELECT *
FROM ((store_sales ss INNER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk) LEFT OUTER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk)
WHERE ss.ss_ticket_number % 1000 = 0;
