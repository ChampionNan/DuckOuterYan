SELECT *
FROM (( catalog_sales FULL OUTER JOIN item ON cs_item_sk = i_item_sk) INNER JOIN ( customer LEFT OUTER JOIN date_dim ON 1=1) ON cs_bill_customer_sk = c_customer_sk)
WHERE c_customer_sk % 3 = 0;
