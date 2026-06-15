SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((web_sales FULL OUTER JOIN customer ON ws_bill_customer_sk=c_customer_sk) RIGHT OUTER JOIN item ON ws_item_sk=i_item_sk);
