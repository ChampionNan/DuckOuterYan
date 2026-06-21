SELECT *
FROM ((( store_sales RIGHT OUTER JOIN item ON ss_item_sk = i_item_sk) INNER JOIN ( customer FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk) LEFT OUTER JOIN ( customer_demographics RIGHT OUTER JOIN household_demographics ON 1=1) ON c_current_cdemo_sk = cd_demo_sk)
WHERE ws_quantity BETWEEN 50 AND 5000;
