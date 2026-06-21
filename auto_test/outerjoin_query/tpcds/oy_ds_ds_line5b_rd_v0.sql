SELECT *
FROM web_sales RIGHT OUTER JOIN (item INNER JOIN (customer FULL OUTER JOIN (customer_demographics LEFT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk) ON c_current_cdemo_sk = cd_demo_sk) ON ws_bill_customer_sk = c_customer_sk) ON ws_item_sk = i_item_sk
WHERE ws_quantity > 0 AND ws_quantity < 10000;
