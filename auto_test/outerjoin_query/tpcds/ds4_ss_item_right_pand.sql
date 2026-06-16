SELECT * FROM store_sales RIGHT OUTER JOIN item ON ss_item_sk=i_item_sk WHERE ss_item_sk > 1 AND ss_item_sk % 2 = 0;
