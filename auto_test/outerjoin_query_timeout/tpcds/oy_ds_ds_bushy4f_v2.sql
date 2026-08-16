SELECT *
FROM (( catalog_sales FULL OUTER JOIN item ON cs_item_sk = i_item_sk) LEFT OUTER JOIN ( customer RIGHT OUTER JOIN date_dim ON 1=1) ON cs_bill_customer_sk = c_customer_sk)
WHERE cs_item_sk > 100;
