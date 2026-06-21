SELECT *
FROM web_sales
    RIGHT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
WHERE i_current_price % 7 <> 0;
