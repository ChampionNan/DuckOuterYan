SELECT *
FROM (( store_sales LEFT OUTER JOIN item ON ss_item_sk = i_item_sk) INNER JOIN ( customer RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk)
WHERE c_customer_sk IN (1, 5, 10, 50, 100, 500);
