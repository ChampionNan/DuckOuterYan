SELECT i_category, MAX(ss_sales_price) AS hi_val
FROM store_sales
    FULL OUTER JOIN item ON ss_item_sk = i_item_sk
    RIGHT OUTER JOIN store ON ss_store_sk = s_store_sk
WHERE ss_quantity >= 100 AND ss_quantity <= 9000
GROUP BY i_category;
