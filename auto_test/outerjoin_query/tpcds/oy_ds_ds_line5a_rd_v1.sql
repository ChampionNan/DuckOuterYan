SELECT *
FROM store_sales FULL OUTER JOIN (item INNER JOIN (store LEFT OUTER JOIN (customer INNER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk) ON ss_store_sk = s_store_sk) ON ss_item_sk = i_item_sk
WHERE ws_item_sk % 7 <> 0;
