-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRF; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRF; relation and predicate structure unchanged
SELECT *
FROM web_sales
    INNER JOIN item ON ws_item_sk = i_item_sk
    LEFT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
    FULL OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE i_current_price % 3 = 0;
