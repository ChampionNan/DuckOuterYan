SELECT * FROM store_sales LEFT OUTER JOIN customer ON ss_customer_sk=c_customer_sk LEFT OUTER JOIN store ON ss_store_sk=s_store_sk WHERE ss_item_sk < 5 OR ss_item_sk % 2 = 0;
