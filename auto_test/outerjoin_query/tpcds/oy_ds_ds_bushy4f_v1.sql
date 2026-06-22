SELECT *
FROM (( catalog_sales RIGHT OUTER JOIN item ON cs_item_sk = i_item_sk) FULL OUTER JOIN ( customer LEFT OUTER JOIN date_dim ON 1=1) ON cs_bill_customer_sk = c_customer_sk)
WHERE i_current_price >= 100 AND i_current_price <= 9000;
