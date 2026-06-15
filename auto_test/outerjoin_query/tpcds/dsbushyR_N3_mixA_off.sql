SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (store_sales LEFT OUTER JOIN (customer INNER JOIN customer_address ON c_current_addr_sk=ca_address_sk) ON ss_customer_sk=c_customer_sk);
