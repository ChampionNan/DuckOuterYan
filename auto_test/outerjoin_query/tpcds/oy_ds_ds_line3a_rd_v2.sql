SELECT *
FROM store_sales RIGHT OUTER JOIN (customer LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk
WHERE ca_address_sk BETWEEN 1 AND 100;
