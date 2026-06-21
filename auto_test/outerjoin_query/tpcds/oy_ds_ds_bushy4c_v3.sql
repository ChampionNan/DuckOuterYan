SELECT *
FROM (( store_sales LEFT OUTER JOIN web_sales ON ss_customer_sk = ws_bill_customer_sk) INNER JOIN ( customer RIGHT OUTER JOIN item ON 1=1) ON ss_customer_sk = c_customer_sk)
WHERE cs_quantity % 7 <> 0;
