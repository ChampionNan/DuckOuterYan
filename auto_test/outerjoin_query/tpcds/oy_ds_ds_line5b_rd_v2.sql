SELECT *
FROM web_sales INNER JOIN (item LEFT OUTER JOIN (customer FULL OUTER JOIN (customer_demographics RIGHT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk) ON c_current_cdemo_sk = cd_demo_sk) ON ws_bill_customer_sk = c_customer_sk) ON ws_item_sk = i_item_sk
WHERE cs_sales_price % 2 = 1;
