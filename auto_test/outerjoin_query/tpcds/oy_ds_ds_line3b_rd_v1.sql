SELECT *
FROM web_sales LEFT OUTER JOIN (customer RIGHT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk) ON ws_bill_customer_sk = c_customer_sk
WHERE cd_demo_sk IN (2, 4, 6, 8, 10, 12, 14);
