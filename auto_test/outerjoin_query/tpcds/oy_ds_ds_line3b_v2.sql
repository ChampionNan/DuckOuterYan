SELECT *
FROM web_sales
    FULL OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
WHERE s_store_sk BETWEEN 1 AND 100;
