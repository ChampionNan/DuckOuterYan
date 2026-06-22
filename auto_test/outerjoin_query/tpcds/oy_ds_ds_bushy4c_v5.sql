SELECT *
FROM (( store_sales FULL OUTER JOIN web_sales ON ss_customer_sk = ws_bill_customer_sk) INNER JOIN ( customer LEFT OUTER JOIN item ON 1=1) ON ss_customer_sk = c_customer_sk)
WHERE c_customer_sk <= 1000;
