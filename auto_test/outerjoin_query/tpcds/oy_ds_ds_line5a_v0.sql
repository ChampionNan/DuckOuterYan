SELECT *
FROM store_sales
    LEFT OUTER JOIN item ON ss_item_sk = i_item_sk
    RIGHT OUTER JOIN store ON ss_store_sk = s_store_sk
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
WHERE i_wholesale_cost IN (1, 5, 10, 50, 100, 500);
