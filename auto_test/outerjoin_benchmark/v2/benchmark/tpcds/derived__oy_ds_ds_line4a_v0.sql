SELECT *
FROM store_sales
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    FULL OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
WHERE cd_demo_sk <= 1000;
