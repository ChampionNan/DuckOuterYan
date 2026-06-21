SELECT *
FROM (( web_sales FULL OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk) LEFT OUTER JOIN ( item RIGHT OUTER JOIN date_dim ON 1=1) ON ws_item_sk = i_item_sk)
WHERE ca_address_sk IN (1, 5, 10, 50, 100, 500);
