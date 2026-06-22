SELECT ca_state, MAX(ss_net_profit) AS hi_val
FROM store_sales
    RIGHT OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
WHERE ss_quantity IN (1, 5, 10, 50, 100, 500)
GROUP BY ca_state;
