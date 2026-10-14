-- corpus_revision: balanced-screened-20261002; component: tpcds-recovery-20261005
-- historical_pattern: derived__ojb_tpcds_q80_store_channel_rdax_sel001
-- source: TPC-DS Q80
-- selectivity: medium; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=global_count
SELECT COUNT(*) AS row_count
FROM (item i LEFT OUTER JOIN (store s INNER JOIN (store_returns sr RIGHT OUTER JOIN (store_sales ss FULL OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_item_sk = sr.sr_item_sk) ON ss.ss_store_sk = s.s_store_sk) ON ss.ss_item_sk = i.i_item_sk)
WHERE (ss.ss_ticket_number % 100) < 30;
