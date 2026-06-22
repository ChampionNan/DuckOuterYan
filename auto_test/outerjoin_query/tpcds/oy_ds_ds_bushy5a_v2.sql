SELECT *
FROM ((( store_sales FULL OUTER JOIN item ON ss_item_sk = i_item_sk) LEFT OUTER JOIN store ON ss_store_sk = s_store_sk) RIGHT OUTER JOIN ( customer FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk)
WHERE s_store_sk > 100;
