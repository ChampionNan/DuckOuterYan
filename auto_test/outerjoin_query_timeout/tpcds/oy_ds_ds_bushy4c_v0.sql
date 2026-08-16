SELECT *
FROM (( store_sales LEFT OUTER JOIN web_sales ON ss_customer_sk = ws_bill_customer_sk) RIGHT OUTER JOIN ( customer FULL OUTER JOIN item ON 1=1) ON ss_customer_sk = c_customer_sk)
WHERE i_item_sk > 0 AND i_item_sk < 10000;
