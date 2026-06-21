SELECT *
FROM web_sales
    RIGHT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    LEFT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE d_year % 7 <> 0;
