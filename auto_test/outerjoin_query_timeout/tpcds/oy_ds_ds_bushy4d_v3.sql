SELECT *
FROM (( store_sales LEFT OUTER JOIN item ON ss_item_sk = i_item_sk) INNER JOIN ( customer RIGHT OUTER JOIN date_dim ON 1=1) ON ss_customer_sk = c_customer_sk)
WHERE i_item_sk IN (1, 5, 10, 50, 100, 500);
