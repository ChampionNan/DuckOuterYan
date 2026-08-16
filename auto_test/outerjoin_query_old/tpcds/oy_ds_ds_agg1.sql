SELECT ca_state, SUM(ss_net_profit) AS total_val
FROM store_sales
    RIGHT OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
WHERE ss_quantity < 50000
GROUP BY ca_state;
