SELECT *
FROM web_sales
    FULL OUTER JOIN item ON ws_item_sk = i_item_sk
    LEFT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
    FULL OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE i_wholesale_cost BETWEEN 50 AND 5000;
