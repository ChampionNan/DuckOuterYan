-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: graph__tpcds__ds_real_catalog_demo__left_deep__lrf__02d6d2e9__sel_low
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT cs_item_sk, cs_sales_price, cd_gender, i_category
FROM catalog_sales
    LEFT OUTER JOIN customer               ON cs_bill_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_demographics  ON c_current_cdemo_sk = cd_demo_sk
    RIGHT OUTER JOIN item                   ON cs_item_sk = i_item_sk
WHERE catalog_sales.cs_quantity <= 3;
