-- query_type: graph; family: tpcds
-- source:
-- semantic_filter: tpcds_store_quantity; tier=low; store sales order-quantity ceiling
-- predicate: store_sales.ss_quantity <= 3
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT ss_item_sk, ss_net_profit, cd_gender, hd_demo_sk, ca_state
FROM store_sales
    RIGHT OUTER JOIN customer               ON ss_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_demographics  ON c_current_cdemo_sk = cd_demo_sk
    INNER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
    LEFT OUTER JOIN customer_address       ON c_current_addr_sk = ca_address_sk
WHERE store_sales.ss_quantity <= 3;
