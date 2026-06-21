SELECT *
FROM store_sales INNER JOIN (customer LEFT OUTER JOIN (customer_address FULL OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk) ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk
WHERE ss_item_sk <= 1000;
