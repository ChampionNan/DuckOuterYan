SELECT *
FROM (( store_sales RIGHT OUTER JOIN store ON ss_store_sk = s_store_sk) INNER JOIN ( customer FULL OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk) ON ss_customer_sk = c_customer_sk)
WHERE c_customer_sk IN (2, 4, 6, 8, 10, 12, 14);
