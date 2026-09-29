-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FIL; relation graph retained; semantic filter replaced
-- semantic_filter: tpcds_web_quantity; tier=low; web sales order-quantity ceiling
-- predicate: web_sales.ws_quantity <= 3
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM web_sales
    FULL OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    INNER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    LEFT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE web_sales.ws_quantity <= 3;
