SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((web_sales LEFT OUTER JOIN customer ON ws_bill_customer_sk=c_customer_sk) LEFT OUTER JOIN item ON ws_item_sk=i_item_sk);
