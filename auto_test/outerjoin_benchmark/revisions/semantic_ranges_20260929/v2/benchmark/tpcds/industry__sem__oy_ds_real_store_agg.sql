-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation and predicate structure unchanged
-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation graph retained; semantic filter replaced
-- semantic_filter: tpcds_store_quantity; tier=high; store sales order-quantity ceiling
-- predicate: store_sales.ss_quantity <= 58
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM store_sales
    LEFT OUTER JOIN item     ON ss_item_sk = i_item_sk
    RIGHT OUTER JOIN store    ON ss_store_sk = s_store_sk
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
WHERE store_sales.ss_quantity <= 58;
