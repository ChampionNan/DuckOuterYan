-- corpus_revision: balanced-screened-20261002; component: tpcds-recovery-20261005
-- historical_pattern: aggregate__tpcds__q93_return_reason_ldmx__fi__global_count__sel_high
-- source: TPC-DS Q93
-- selectivity: low; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=global_count
SELECT COUNT(*) AS row_count
FROM ((store_sales ss FULL OUTER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk) INNER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk)
WHERE r.r_reason_desc = 'reason 28';
