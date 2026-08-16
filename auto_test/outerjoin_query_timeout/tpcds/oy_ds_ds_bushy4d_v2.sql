SELECT *
FROM (( store_sales FULL OUTER JOIN item ON ss_item_sk = i_item_sk) LEFT OUTER JOIN ( customer RIGHT OUTER JOIN date_dim ON 1=1) ON ss_customer_sk = c_customer_sk)
WHERE c_customer_sk <= 1000;
