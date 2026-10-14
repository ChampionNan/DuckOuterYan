-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Industry-inspired synthetic control graph__tpcds__ds_real_catalog_demo__lrf__sel_medium
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT cs_item_sk, cs_sales_price, cd_gender, i_category
FROM catalog_sales
    LEFT OUTER JOIN customer               ON cs_bill_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_demographics  ON c_current_cdemo_sk = cd_demo_sk
    FULL OUTER JOIN item                   ON cs_item_sk = i_item_sk
WHERE catalog_sales.cs_quantity <= 3;