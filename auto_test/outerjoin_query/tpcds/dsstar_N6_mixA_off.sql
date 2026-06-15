SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (((((store_sales LEFT OUTER JOIN item ON ss_item_sk=i_item_sk) INNER JOIN customer ON ss_customer_sk=c_customer_sk) RIGHT OUTER JOIN store ON ss_store_sk=s_store_sk) FULL OUTER JOIN customer_address ON ss_addr_sk=ca_address_sk) LEFT OUTER JOIN promotion ON ss_promo_sk=p_promo_sk);
