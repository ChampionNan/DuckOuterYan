SELECT * FROM store_sales RIGHT OUTER JOIN item ON ss_item_sk=i_item_sk WHERE ss_item_sk < 5 OR ss_item_sk % 2 = 0;
