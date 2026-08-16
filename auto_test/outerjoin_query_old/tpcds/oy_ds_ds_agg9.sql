SELECT d_year, SUM(ws_sales_price) AS total_val
FROM web_sales
    RIGHT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    FULL OUTER JOIN date_dim ON ws_sold_date_sk = d_date_sk
WHERE ws_quantity >= 10
GROUP BY d_year;
