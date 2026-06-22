SELECT *
FROM web_sales LEFT OUTER JOIN (customer RIGHT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk) ON ws_bill_customer_sk = c_customer_sk
WHERE c_customer_sk < 200;
