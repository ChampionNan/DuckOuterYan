-- corpus_revision: balanced-screened-20261002; component: tpcds-recovery-20261005
-- historical_pattern: aggregate__tpcds__q93_return_reason_ldmx__fi__global_count__sel_high
-- source: TPC-DS Q93
-- selectivity: high; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=global_count
SELECT COUNT(*) AS row_count
FROM ((store_sales ss FULL OUTER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk) INNER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk)
WHERE (r.r_reason_desc = 'reason 28' OR r.r_reason_desc = 'Did not fit' OR r.r_reason_desc = 'Wrong size' OR r.r_reason_desc = 'Did not like the color' OR r.r_reason_desc = 'Did not like the make' OR r.r_reason_desc = 'Did not like the model' OR r.r_reason_desc = 'Not the product that was ordred' OR r.r_reason_desc = 'Does not work with a product that I have' OR r.r_reason_desc = 'Did not get it on time' OR r.r_reason_desc = 'Did not like the warranty' OR r.r_reason_desc = 'Found a better extended warranty in a store' OR r.r_reason_desc = 'Found a better price in a store' OR r.r_reason_desc = 'Gift exchange' OR r.r_reason_desc = 'Lost my job' OR r.r_reason_desc = 'No service location in my area' OR r.r_reason_desc = 'Not working any more' OR r.r_reason_desc = 'Package was damaged' OR r.r_reason_desc = 'Parts missing' OR r.r_reason_desc = 'Stopped working' OR r.r_reason_desc = 'duplicate purchase' OR r.r_reason_desc = 'unauthoized purchase');
