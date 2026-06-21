SELECT *
FROM (( store_sales RIGHT OUTER JOIN web_sales ON ss_customer_sk = ws_bill_customer_sk) INNER JOIN ( customer FULL OUTER JOIN item ON 1=1) ON ss_customer_sk = c_customer_sk)
WHERE d_date_sk BETWEEN 1 AND 100;
