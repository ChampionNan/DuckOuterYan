SELECT *
FROM (( store_sales RIGHT OUTER JOIN web_sales ON ss_customer_sk = ws_bill_customer_sk) FULL OUTER JOIN ( customer LEFT OUTER JOIN item ON 1=1) ON ss_customer_sk = c_customer_sk)
WHERE ws_item_sk <= 1000;
