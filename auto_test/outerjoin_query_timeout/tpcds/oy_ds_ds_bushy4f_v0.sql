SELECT *
FROM (( catalog_sales LEFT OUTER JOIN item ON cs_item_sk = i_item_sk) RIGHT OUTER JOIN ( customer FULL OUTER JOIN date_dim ON 1=1) ON cs_bill_customer_sk = c_customer_sk)
WHERE c_birth_year > 500;
