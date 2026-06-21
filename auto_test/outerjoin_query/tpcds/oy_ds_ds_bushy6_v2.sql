SELECT *
FROM ((( store_sales FULL OUTER JOIN item ON ss_item_sk = i_item_sk) LEFT OUTER JOIN ( customer RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk) FULL OUTER JOIN ( customer_demographics LEFT OUTER JOIN household_demographics ON 1=1) ON c_current_cdemo_sk = cd_demo_sk)
WHERE ss_quantity > 100;
