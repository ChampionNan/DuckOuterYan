-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILR; relation and predicate structure unchanged
SELECT *
FROM web_sales
    INNER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    RIGHT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE ws_item_sk BETWEEN 50 AND 5000;
