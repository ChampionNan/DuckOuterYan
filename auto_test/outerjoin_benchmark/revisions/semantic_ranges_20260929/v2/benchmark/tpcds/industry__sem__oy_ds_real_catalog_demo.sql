-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation and predicate structure unchanged
-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILR; relation graph retained; semantic filter replaced
-- semantic_filter: tpcds_catalog_quantity; tier=medium; catalog sales order-quantity ceiling
-- predicate: catalog_sales.cs_quantity <= 30
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT cs_item_sk, cs_sales_price, cd_gender, i_category
FROM catalog_sales
    LEFT OUTER JOIN customer               ON cs_bill_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_demographics  ON c_current_cdemo_sk = cd_demo_sk
    FULL OUTER JOIN item                   ON cs_item_sk = i_item_sk
WHERE catalog_sales.cs_quantity <= 30;
