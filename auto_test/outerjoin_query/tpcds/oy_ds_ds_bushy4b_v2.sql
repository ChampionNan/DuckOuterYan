SELECT *
FROM (( web_sales FULL OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk) LEFT OUTER JOIN ( item RIGHT OUTER JOIN date_dim ON 1=1) ON ws_item_sk = i_item_sk)
WHERE i_item_sk BETWEEN 1 AND 100;
