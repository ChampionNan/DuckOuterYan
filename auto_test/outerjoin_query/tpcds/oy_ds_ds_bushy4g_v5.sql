SELECT *
FROM (( store_sales FULL OUTER JOIN store ON ss_store_sk = s_store_sk) INNER JOIN ( customer LEFT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk) ON ss_customer_sk = c_customer_sk)
WHERE cd_demo_sk % 2 = 1;
