SELECT i_category, AVG(ss_sales_price) AS avg_price
FROM store_sales
    RIGHT OUTER JOIN item ON ss_item_sk = i_item_sk
    RIGHT OUTER JOIN store ON ss_store_sk = s_store_sk
WHERE cs_sales_price > 0 AND cs_sales_price < 10000
GROUP BY i_category;
