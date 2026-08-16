SELECT *
FROM (( store_sales LEFT OUTER JOIN store ON ss_store_sk = s_store_sk) RIGHT OUTER JOIN ( customer FULL OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk) ON ss_customer_sk = c_customer_sk)
WHERE cd_demo_sk >= 10;
