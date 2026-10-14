-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-DS Q93
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ss.ss_item_sk, sr.sr_item_sk, ss.ss_ticket_number, sr.sr_ticket_number, sr.sr_reason_sk, r.r_reason_sk
FROM ((store_returns sr INNER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk) LEFT OUTER JOIN store_sales ss ON ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number)
WHERE r.r_reason_desc = 'reason 28';
