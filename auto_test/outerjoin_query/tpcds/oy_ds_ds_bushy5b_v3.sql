SELECT *
FROM ((( store_sales LEFT OUTER JOIN item ON ss_item_sk = i_item_sk) INNER JOIN promotion ON ss_promo_sk = p_promo_sk) RIGHT OUTER JOIN ( customer FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ss_customer_sk = c_customer_sk)
WHERE ss_sales_price < 200;
