SELECT ca_state, COUNT(*) AS cnt, SUM(ss_net_profit) AS profit
FROM store_sales
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
WHERE cs_item_sk % 3 = 0
GROUP BY ca_state;
