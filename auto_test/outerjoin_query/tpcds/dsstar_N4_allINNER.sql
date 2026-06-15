SELECT * FROM (((store_sales INNER JOIN item ON ss_item_sk=i_item_sk) INNER JOIN customer ON ss_customer_sk=c_customer_sk) INNER JOIN store ON ss_store_sk=s_store_sk);
