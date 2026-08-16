SELECT *
FROM store_sales FULL OUTER JOIN (customer FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk
WHERE ss_item_sk IN (2, 4, 6, 8, 10, 12, 14);
