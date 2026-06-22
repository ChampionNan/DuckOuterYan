SELECT d_year, COUNT(*) AS cnt_val
FROM web_sales
    LEFT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
    RIGHT OUTER JOIN date_dim ON ws_sold_date_sk = d_date_sk
WHERE ws_quantity > 100
GROUP BY d_year;
