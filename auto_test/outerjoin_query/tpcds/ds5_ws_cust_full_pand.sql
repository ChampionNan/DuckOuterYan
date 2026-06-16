SELECT * FROM web_sales FULL OUTER JOIN customer ON ws_bill_customer_sk=c_customer_sk WHERE ws_item_sk > 1 AND ws_item_sk % 2 = 0;
