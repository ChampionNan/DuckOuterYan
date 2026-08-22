SELECT ws_item_sk, ws_sales_price, c_last_name, ca_state, d_year
FROM web_sales
    LEFT OUTER JOIN customer         ON ws_bill_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    LEFT OUTER JOIN date_dim         ON ws_sold_date_sk = d_date_sk
WHERE ws_quantity > 0;
