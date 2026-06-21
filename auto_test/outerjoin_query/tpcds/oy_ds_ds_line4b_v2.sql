SELECT *
FROM web_sales
    FULL OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    RIGHT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE p_promo_sk BETWEEN 1 AND 100;
