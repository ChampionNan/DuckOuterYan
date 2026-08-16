SELECT *
FROM (( store_sales LEFT OUTER JOIN store ON ss_store_sk = s_store_sk) INNER JOIN ( customer RIGHT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk) ON ss_customer_sk = c_customer_sk)
WHERE ss_sales_price > 0 AND ss_sales_price < 10000;
