SELECT *
FROM (( catalog_sales RIGHT OUTER JOIN item ON cs_item_sk = i_item_sk) INNER JOIN ( customer FULL OUTER JOIN date_dim ON 1=1) ON cs_bill_customer_sk = c_customer_sk)
WHERE d_year BETWEEN 50 AND 5000;
