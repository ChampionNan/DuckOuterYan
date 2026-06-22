SELECT ca_state, COUNT(*) AS cnt_val
FROM store_sales
    LEFT OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
WHERE ss_quantity < 200
GROUP BY ca_state;
