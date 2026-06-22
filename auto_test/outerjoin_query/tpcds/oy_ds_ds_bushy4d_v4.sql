SELECT *
FROM (( store_sales RIGHT OUTER JOIN item ON ss_item_sk = i_item_sk) INNER JOIN ( customer FULL OUTER JOIN date_dim ON 1=1) ON ss_customer_sk = c_customer_sk)
WHERE i_wholesale_cost % 7 <> 0;
