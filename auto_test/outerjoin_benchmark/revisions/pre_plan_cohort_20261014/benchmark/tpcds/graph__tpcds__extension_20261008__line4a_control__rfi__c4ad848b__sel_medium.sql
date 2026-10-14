-- corpus_revision: balanced-screened-20261002; component: tpcds-selectivity-extension-20261008
-- historical_pattern: derived__oy_ds_ds_line4a_v0
-- source: Industry-inspired synthetic control
-- selectivity: medium; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=preserve_select_star
SELECT *
FROM store_sales
    RIGHT OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    INNER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
WHERE customer_demographics.cd_demo_sk <= 576240;
