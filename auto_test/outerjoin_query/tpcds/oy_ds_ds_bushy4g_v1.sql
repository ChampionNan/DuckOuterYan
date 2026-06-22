SELECT *
FROM (( store_sales RIGHT OUTER JOIN store ON ss_store_sk = s_store_sk) FULL OUTER JOIN ( customer LEFT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk) ON ss_customer_sk = c_customer_sk)
WHERE s_store_sk BETWEEN 50 AND 5000;
