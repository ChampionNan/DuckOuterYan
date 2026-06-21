SELECT *
FROM (( store_sales FULL OUTER JOIN web_sales ON ss_customer_sk = ws_bill_customer_sk) LEFT OUTER JOIN ( customer RIGHT OUTER JOIN item ON 1=1) ON ss_customer_sk = c_customer_sk)
WHERE ws_sales_price IN (1, 5, 10, 50, 100, 500);
