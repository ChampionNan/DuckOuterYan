SELECT *
FROM web_sales
    RIGHT OUTER JOIN item ON ws_item_sk = i_item_sk
    INNER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
    LEFT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE ss_quantity > 0 AND ss_quantity < 10000;
