SELECT *
FROM web_sales
    LEFT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    FULL OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE ws_item_sk BETWEEN 50 AND 5000;
