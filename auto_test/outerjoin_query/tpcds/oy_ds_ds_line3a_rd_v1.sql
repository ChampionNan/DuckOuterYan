SELECT *
FROM store_sales LEFT OUTER JOIN (customer RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk
WHERE c_customer_sk % 7 <> 0;
