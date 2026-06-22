SELECT *
FROM ((( store_sales RIGHT OUTER JOIN item ON ss_item_sk = i_item_sk) FULL OUTER JOIN promotion ON ss_promo_sk = p_promo_sk) LEFT OUTER JOIN ( customer RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk)
WHERE i_current_price IN (2, 4, 6, 8, 10, 12, 14);
