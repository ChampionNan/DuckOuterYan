SELECT i_category, count(ss_item_sk) AS sold_cnt
FROM store_sales
    LEFT OUTER JOIN item     ON ss_item_sk = i_item_sk
    LEFT OUTER JOIN store    ON ss_store_sk = s_store_sk
    LEFT OUTER JOIN customer ON ss_customer_sk = c_customer_sk
WHERE ss_quantity > 0
GROUP BY i_category;
