SELECT *
FROM ((( store_sales RIGHT OUTER JOIN item ON ss_item_sk = i_item_sk) FULL OUTER JOIN store ON ss_store_sk = s_store_sk) LEFT OUTER JOIN ( customer RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk)
WHERE hd_demo_sk > 0 AND hd_demo_sk < 10000;
