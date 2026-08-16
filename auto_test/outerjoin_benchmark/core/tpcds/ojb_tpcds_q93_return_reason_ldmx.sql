-- source: TPC-DS Q93
-- transformation: connected join-subgraph adaptation; primary left-deep mixed join labeling
-- business_semantics: Store-sale records are associated with optional returns and their reason dimension.
SELECT *
FROM ((store_sales ss FULL OUTER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number) RIGHT OUTER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk)
WHERE (ss.ss_ticket_number % 1000 = 0 OR ss.ss_ticket_number IS NULL);
