SELECT *
FROM store_sales RIGHT OUTER JOIN (item INNER JOIN (store FULL OUTER JOIN (customer LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk) ON ss_store_sk = s_store_sk) ON ss_item_sk = i_item_sk
WHERE ss_sales_price IN (1, 5, 10, 50, 100, 500);
