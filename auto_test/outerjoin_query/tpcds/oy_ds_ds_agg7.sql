SELECT i_brand, COUNT(*) AS cnt, SUM(ws_quantity) AS tot_qty
FROM web_sales
    RIGHT OUTER JOIN item ON ws_item_sk = i_item_sk
    FULL OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk
WHERE i_item_sk IN (1, 5, 10, 50, 100, 500)
GROUP BY i_brand;
