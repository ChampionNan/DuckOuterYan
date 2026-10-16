-- query_type: graph; family: tpcds
-- source:
-- semantic_filter: tpcds_store_quantity; tier=high; store sales order-quantity ceiling
-- predicate: store_sales.ss_quantity <= 58
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM store_sales
    LEFT OUTER JOIN item     ON ss_item_sk = i_item_sk
    RIGHT OUTER JOIN store    ON ss_store_sk = s_store_sk
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
WHERE store_sales.ss_quantity <= 58;
