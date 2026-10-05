-- corpus_revision: balanced-screened-20261002; component: tpcds-recovery-20261005
-- historical_pattern: graph__tpcds__ds_ds_line4b__fil__sel_low
-- source: Industry-inspired synthetic control
-- selectivity: high; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=archive_projection
SELECT *
FROM web_sales
    FULL OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    INNER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    LEFT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE web_sales.ws_quantity <= 55;
