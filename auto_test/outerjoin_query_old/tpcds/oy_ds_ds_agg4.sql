SELECT i_category, COUNT(*) AS cnt_val
FROM store_sales
    FULL OUTER JOIN item ON ss_item_sk = i_item_sk
    FULL OUTER JOIN store ON ss_store_sk = s_store_sk
WHERE ss_quantity % 7 <> 0
GROUP BY i_category;
