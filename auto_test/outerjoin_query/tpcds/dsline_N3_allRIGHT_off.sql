SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((store_sales RIGHT OUTER JOIN customer ON ss_customer_sk=c_customer_sk) RIGHT OUTER JOIN customer_address ON c_current_addr_sk=ca_address_sk);
