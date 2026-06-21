SELECT *
FROM web_sales RIGHT OUTER JOIN (customer LEFT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk) ON ws_bill_customer_sk = c_customer_sk
WHERE hd_demo_sk % 2 = 1;
