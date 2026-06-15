SELECT * FROM ((store_sales FULL OUTER JOIN item ON ss_item_sk=i_item_sk) RIGHT OUTER JOIN (customer INNER JOIN customer_address ON c_current_addr_sk=ca_address_sk) ON ss_customer_sk=c_customer_sk);
