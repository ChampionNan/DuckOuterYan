SELECT *
FROM store_sales INNER JOIN (item LEFT OUTER JOIN (store FULL OUTER JOIN (customer RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk) ON ss_store_sk = s_store_sk) ON ss_item_sk = i_item_sk
WHERE ws_sales_price BETWEEN 1 AND 100;
