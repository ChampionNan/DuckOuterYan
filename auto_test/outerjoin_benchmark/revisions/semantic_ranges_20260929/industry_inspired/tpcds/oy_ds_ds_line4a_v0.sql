-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation graph retained; semantic filter replaced
-- semantic_filter: tpcds_store_quantity; tier=high; store sales order-quantity ceiling
-- predicate: store_sales.ss_quantity <= 58
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM store_sales
    RIGHT OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    INNER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
WHERE store_sales.ss_quantity <= 58;
