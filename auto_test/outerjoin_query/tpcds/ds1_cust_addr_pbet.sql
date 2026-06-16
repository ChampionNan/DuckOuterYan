SELECT * FROM customer LEFT OUTER JOIN customer_address ON c_current_addr_sk=ca_address_sk WHERE c_customer_sk BETWEEN 1 AND 1000;
