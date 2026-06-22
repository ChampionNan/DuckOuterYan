SELECT *
FROM ((( store_sales FULL OUTER JOIN item ON ss_item_sk = i_item_sk) LEFT OUTER JOIN promotion ON ss_promo_sk = p_promo_sk) RIGHT OUTER JOIN ( customer FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk)
WHERE ss_item_sk % 2 = 1;
