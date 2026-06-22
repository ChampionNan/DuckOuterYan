SELECT *
FROM (( store_sales FULL OUTER JOIN web_sales ON ss_customer_sk = ws_bill_customer_sk) LEFT OUTER JOIN ( customer RIGHT OUTER JOIN item ON 1=1) ON ss_customer_sk = c_customer_sk)
WHERE ss_quantity % 2 = 1;
