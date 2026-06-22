SELECT d_year, MAX(ws_sales_price) AS hi_val
FROM web_sales
    RIGHT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    RIGHT OUTER JOIN date_dim ON ws_sold_date_sk = d_date_sk
WHERE ws_quantity % 3 = 0
GROUP BY d_year;
