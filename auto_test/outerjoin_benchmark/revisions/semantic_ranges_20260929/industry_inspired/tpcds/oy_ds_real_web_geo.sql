-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation graph retained; semantic filter replaced
-- semantic_filter: tpcds_web_quantity; tier=high; web sales order-quantity ceiling
-- predicate: web_sales.ws_quantity <= 55
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT ws_item_sk, ws_sales_price, c_last_name, ca_state, d_year
FROM web_sales
    RIGHT OUTER JOIN customer         ON ws_bill_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    INNER JOIN date_dim         ON ws_sold_date_sk = d_date_sk
WHERE web_sales.ws_quantity <= 55;
