SELECT ca_state, MIN(ss_net_profit) AS lo_val
FROM store_sales
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
WHERE ss_quantity <= 1000
GROUP BY ca_state;
