SELECT *
FROM web_sales FULL OUTER JOIN (customer FULL OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk) ON ws_bill_customer_sk = c_customer_sk
WHERE ws_quantity % 2 = 1;
