-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILR; relation and predicate structure unchanged
SELECT *
FROM web_sales
    RIGHT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    INNER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE ws_item_sk BETWEEN 50 AND 5000;
