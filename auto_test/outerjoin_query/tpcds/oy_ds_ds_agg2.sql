SELECT d_year, COUNT(*) AS cnt, SUM(ws_sales_price) AS tot
FROM web_sales
    FULL OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    FULL OUTER JOIN date_dim ON ws_sold_date_sk = d_date_sk
WHERE d_year IN (2, 4, 6, 8, 10, 12, 14)
GROUP BY d_year;
