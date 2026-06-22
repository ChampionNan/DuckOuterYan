SELECT i_item_sk, i_brand, ss_sales_price, cs_sales_price, d_year
FROM item
    LEFT OUTER JOIN store_sales   ON i_item_sk = ss_item_sk
    FULL OUTER JOIN catalog_sales ON i_item_sk = cs_item_sk
    LEFT OUTER JOIN date_dim      ON ss_sold_date_sk = d_date_sk
WHERE i_category IS NOT NULL;
