SELECT *
FROM (( web_sales RIGHT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk) INNER JOIN ( item FULL OUTER JOIN date_dim ON 1=1) ON ws_item_sk = i_item_sk)
WHERE ws_quantity >= 100 AND ws_quantity <= 9000;
