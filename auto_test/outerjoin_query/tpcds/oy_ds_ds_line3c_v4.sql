SELECT *
FROM store_sales
    FULL OUTER JOIN item ON ss_item_sk = i_item_sk
    FULL OUTER JOIN date_dim ON ss_sold_date_sk = d_date_sk
WHERE cs_item_sk <= 1000;
