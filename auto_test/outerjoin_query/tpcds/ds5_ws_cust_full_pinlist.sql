SELECT * FROM web_sales FULL OUTER JOIN customer ON ws_bill_customer_sk=c_customer_sk WHERE ws_item_sk IN (1, 2, 3, 5, 8, 13);
