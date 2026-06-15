SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (((store_sales RIGHT OUTER JOIN item ON ss_item_sk=i_item_sk) FULL OUTER JOIN customer ON ss_customer_sk=c_customer_sk) LEFT OUTER JOIN store ON ss_store_sk=s_store_sk);
