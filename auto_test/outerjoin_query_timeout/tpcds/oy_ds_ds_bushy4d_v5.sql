SELECT *
FROM (( store_sales FULL OUTER JOIN item ON ss_item_sk = i_item_sk) INNER JOIN ( customer LEFT OUTER JOIN date_dim ON 1=1) ON ss_customer_sk = c_customer_sk)
WHERE ss_quantity BETWEEN 1 AND 100;
