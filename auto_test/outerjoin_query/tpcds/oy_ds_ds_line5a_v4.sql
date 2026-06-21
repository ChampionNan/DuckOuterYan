SELECT *
FROM store_sales
    RIGHT OUTER JOIN item ON ss_item_sk = i_item_sk
    INNER JOIN store ON ss_store_sk = s_store_sk
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
WHERE i_current_price <= 1000;
