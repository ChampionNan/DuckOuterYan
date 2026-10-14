-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-DS Q80
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ss.ss_item_sk, sr.sr_item_sk, ss.ss_ticket_number, sr.sr_ticket_number, ss.ss_sold_date_sk, d.d_date_sk, ss.ss_store_sk, s.s_store_sk, i.i_item_sk
FROM ((((store_sales ss INNER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number) FULL OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) RIGHT OUTER JOIN store s ON ss.ss_store_sk = s.s_store_sk) LEFT OUTER JOIN item i ON ss.ss_item_sk = i.i_item_sk)
WHERE d.d_date BETWEEN DATE '1999-11-09' AND DATE '2001-06-21';
