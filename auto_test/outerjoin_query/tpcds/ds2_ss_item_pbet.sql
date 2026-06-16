SELECT * FROM store_sales LEFT OUTER JOIN item ON ss_item_sk=i_item_sk WHERE ss_item_sk BETWEEN 1 AND 1000;
