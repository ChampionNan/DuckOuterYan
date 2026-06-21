SELECT s_state, MIN(ss_sales_price) AS lo, MAX(ss_sales_price) AS hi
FROM store_sales
    FULL OUTER JOIN item ON ss_item_sk = i_item_sk
    INNER JOIN store ON ss_store_sk = s_store_sk
    LEFT OUTER JOIN customer ON ss_customer_sk = c_customer_sk
WHERE p_promo_sk % 2 = 1
GROUP BY s_state;
