SELECT *
FROM web_sales
    FULL OUTER JOIN item ON ws_item_sk = i_item_sk
    FULL OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
    FULL OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE i_current_price % 3 = 0;
