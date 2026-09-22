-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation and predicate structure unchanged
SELECT *
FROM store_sales
    RIGHT OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    INNER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
WHERE cd_demo_sk <= 1000;
