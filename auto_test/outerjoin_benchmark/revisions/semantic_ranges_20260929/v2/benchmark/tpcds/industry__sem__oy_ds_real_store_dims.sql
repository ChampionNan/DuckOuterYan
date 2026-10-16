-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FILR; relation and predicate structure unchanged
-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FILR; relation graph retained; semantic filter replaced
-- semantic_filter: tpcds_store_quantity; tier=medium; store sales order-quantity ceiling
-- predicate: store_sales.ss_quantity <= 31
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT ss_item_sk, ss_sales_price, i_brand, c_first_name, s_store_name
FROM store_sales
    FULL OUTER JOIN item      ON ss_item_sk = i_item_sk
    INNER JOIN customer  ON ss_customer_sk = c_customer_sk
    LEFT OUTER JOIN store     ON ss_store_sk = s_store_sk
    RIGHT OUTER JOIN promotion ON ss_promo_sk = p_promo_sk
WHERE store_sales.ss_quantity <= 31;
