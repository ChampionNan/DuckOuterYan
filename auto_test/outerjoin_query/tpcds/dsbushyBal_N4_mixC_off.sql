SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((store_sales RIGHT OUTER JOIN item ON ss_item_sk=i_item_sk) FULL OUTER JOIN (customer LEFT OUTER JOIN customer_address ON c_current_addr_sk=ca_address_sk) ON ss_customer_sk=c_customer_sk);
