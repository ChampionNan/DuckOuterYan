SELECT *
FROM store_sales
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
WHERE i_wholesale_cost > 0 AND i_wholesale_cost < 10000;
