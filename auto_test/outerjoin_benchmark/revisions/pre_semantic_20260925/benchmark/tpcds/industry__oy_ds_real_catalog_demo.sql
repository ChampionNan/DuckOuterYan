-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILR; relation and predicate structure unchanged
SELECT cs_item_sk, cs_sales_price, cd_gender, i_category
FROM catalog_sales
    INNER JOIN customer               ON cs_bill_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_demographics  ON c_current_cdemo_sk = cd_demo_sk
    RIGHT OUTER JOIN item                   ON cs_item_sk = i_item_sk
WHERE cs_quantity > 0;
