SELECT cd_gender, COUNT(*) AS cnt, AVG(ss_quantity) AS avg_qty
FROM store_sales
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
WHERE ca_address_sk < 50000
GROUP BY cd_gender;
