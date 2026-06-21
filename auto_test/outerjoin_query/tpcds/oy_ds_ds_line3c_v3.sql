SELECT *
FROM store_sales
    RIGHT OUTER JOIN item ON ss_item_sk = i_item_sk
    RIGHT OUTER JOIN date_dim ON ss_sold_date_sk = d_date_sk
WHERE ws_quantity < 50000;
