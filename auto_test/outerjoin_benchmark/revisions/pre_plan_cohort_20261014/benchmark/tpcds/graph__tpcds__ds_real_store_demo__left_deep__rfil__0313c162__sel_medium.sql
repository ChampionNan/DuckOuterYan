-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Industry-inspired synthetic control graph__tpcds__ds_real_store_demo__rfil__sel_low
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ss_item_sk, ss_net_profit, cd_gender, hd_demo_sk, ca_state
FROM store_sales
    RIGHT OUTER JOIN customer               ON ss_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_demographics  ON c_current_cdemo_sk = cd_demo_sk
    INNER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
    LEFT OUTER JOIN customer_address       ON c_current_addr_sk = ca_address_sk
WHERE store_sales.ss_quantity <= 31;