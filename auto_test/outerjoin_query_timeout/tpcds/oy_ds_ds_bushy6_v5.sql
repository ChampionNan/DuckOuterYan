SELECT *
FROM ((( store_sales FULL OUTER JOIN item ON ss_item_sk = i_item_sk) INNER JOIN ( customer LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk) INNER JOIN ( customer_demographics RIGHT OUTER JOIN household_demographics ON 1=1) ON c_current_cdemo_sk = cd_demo_sk)
WHERE cd_demo_sk % 2 = 1;
