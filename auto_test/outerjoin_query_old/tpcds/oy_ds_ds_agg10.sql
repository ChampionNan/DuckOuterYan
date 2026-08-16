SELECT d_year, MIN(ws_sales_price) AS lo_val
FROM web_sales
    FULL OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    LEFT OUTER JOIN date_dim ON ws_sold_date_sk = d_date_sk
WHERE ws_quantity BETWEEN 50 AND 5000
GROUP BY d_year;
