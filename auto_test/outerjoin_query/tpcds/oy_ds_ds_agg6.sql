SELECT i_category, MIN(ss_sales_price) AS lo_val
FROM store_sales
    RIGHT OUTER JOIN item ON ss_item_sk = i_item_sk
    LEFT OUTER JOIN store ON ss_store_sk = s_store_sk
WHERE ss_quantity > 500
GROUP BY i_category;
