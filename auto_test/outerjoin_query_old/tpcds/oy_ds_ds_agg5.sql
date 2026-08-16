SELECT i_category, SUM(ss_sales_price) AS total_val
FROM store_sales
    LEFT OUTER JOIN item ON ss_item_sk = i_item_sk
    RIGHT OUTER JOIN store ON ss_store_sk = s_store_sk
WHERE ss_quantity BETWEEN 1 AND 100
GROUP BY i_category;
