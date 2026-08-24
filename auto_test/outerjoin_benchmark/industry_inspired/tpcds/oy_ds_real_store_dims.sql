SELECT ss_item_sk, ss_sales_price, i_brand, c_first_name, s_store_name
FROM store_sales
    FULL OUTER JOIN item      ON ss_item_sk = i_item_sk
    FULL OUTER JOIN customer  ON ss_customer_sk = c_customer_sk
    FULL OUTER JOIN store     ON ss_store_sk = s_store_sk
    FULL OUTER JOIN promotion ON ss_promo_sk = p_promo_sk
WHERE ss_quantity > 0;
