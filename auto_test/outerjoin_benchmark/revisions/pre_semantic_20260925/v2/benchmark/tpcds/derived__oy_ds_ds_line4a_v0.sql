-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation and predicate structure unchanged
SELECT *
FROM store_sales
    LEFT OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    FULL OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
WHERE cd_demo_sk <= 1000;
