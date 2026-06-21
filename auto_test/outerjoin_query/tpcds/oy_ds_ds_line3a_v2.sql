SELECT *
FROM store_sales
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
WHERE cd_purchase_estimate BETWEEN 50 AND 5000;
