SELECT *
FROM web_sales FULL OUTER JOIN (item INNER JOIN (customer LEFT OUTER JOIN (customer_demographics INNER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk) ON c_current_cdemo_sk = cd_demo_sk) ON ws_bill_customer_sk = c_customer_sk) ON ws_item_sk = i_item_sk
WHERE cs_item_sk IN (2, 4, 6, 8, 10, 12, 14);
