-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-DS Q93
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ss.ss_item_sk, sr.sr_item_sk, ss.ss_ticket_number, sr.sr_ticket_number, sr.sr_reason_sk, r.r_reason_sk
FROM ((store_returns sr INNER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk) LEFT OUTER JOIN store_sales ss ON ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number)
WHERE (r.r_reason_desc = 'reason 28' OR r.r_reason_desc = 'Did not fit' OR r.r_reason_desc = 'Wrong size' OR r.r_reason_desc = 'Did not like the color' OR r.r_reason_desc = 'Did not like the make' OR r.r_reason_desc = 'Did not like the model' OR r.r_reason_desc = 'Not the product that was ordred' OR r.r_reason_desc = 'Does not work with a product that I have');
