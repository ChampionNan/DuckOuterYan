SELECT *
FROM store_sales FULL OUTER JOIN (customer FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk
WHERE p_promo_sk IN (1, 5, 10, 50, 100, 500);
