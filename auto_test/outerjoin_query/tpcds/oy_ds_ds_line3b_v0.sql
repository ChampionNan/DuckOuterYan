SELECT *
FROM web_sales
    LEFT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
WHERE hd_demo_sk IN (1, 5, 10, 50, 100, 500);
