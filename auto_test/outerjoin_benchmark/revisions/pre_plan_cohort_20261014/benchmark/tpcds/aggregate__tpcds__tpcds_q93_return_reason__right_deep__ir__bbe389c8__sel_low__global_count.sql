-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-DS Q93
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM (store_sales ss INNER JOIN (reason r RIGHT OUTER JOIN store_returns sr ON sr.sr_reason_sk = r.r_reason_sk) ON ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number)
WHERE r.r_reason_desc = 'reason 28';
