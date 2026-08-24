SELECT cs_item_sk, cs_sales_price, cd_gender, i_category
FROM catalog_sales
    FULL OUTER JOIN customer               ON cs_bill_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_demographics  ON c_current_cdemo_sk = cd_demo_sk
    FULL OUTER JOIN item                   ON cs_item_sk = i_item_sk
WHERE cs_quantity > 0;
