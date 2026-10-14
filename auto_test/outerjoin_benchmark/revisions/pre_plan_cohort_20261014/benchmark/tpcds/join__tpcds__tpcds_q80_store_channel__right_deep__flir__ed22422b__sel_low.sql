-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-DS Q80
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ss.ss_item_sk, sr.sr_item_sk, ss.ss_ticket_number, sr.sr_ticket_number, ss.ss_sold_date_sk, d.d_date_sk, ss.ss_store_sk, s.s_store_sk, i.i_item_sk
FROM (item i FULL OUTER JOIN (store s LEFT OUTER JOIN (date_dim d INNER JOIN (store_returns sr RIGHT OUTER JOIN store_sales ss ON ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number) ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_store_sk = s.s_store_sk) ON ss.ss_item_sk = i.i_item_sk)
WHERE d.d_date BETWEEN DATE '2000-08-09' AND DATE '2000-09-20';
