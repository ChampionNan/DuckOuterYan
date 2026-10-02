-- query_type: graph; family: tpcds
-- source:
-- semantic_filter: tpcds_web_quantity; tier=medium; web sales order-quantity ceiling
-- predicate: web_sales.ws_quantity <= 30
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM web_sales
    INNER JOIN item ON ws_item_sk = i_item_sk
    LEFT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
    FULL OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE web_sales.ws_quantity <= 30;
