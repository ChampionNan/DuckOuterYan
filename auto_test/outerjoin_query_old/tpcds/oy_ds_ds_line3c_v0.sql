SELECT *
FROM store_sales
    LEFT OUTER JOIN item ON ss_item_sk = i_item_sk
    RIGHT OUTER JOIN date_dim ON ss_sold_date_sk = d_date_sk
WHERE i_wholesale_cost >= 10;
