SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((web_sales INNER JOIN customer ON ws_bill_customer_sk=c_customer_sk) INNER JOIN item ON ws_item_sk=i_item_sk);
