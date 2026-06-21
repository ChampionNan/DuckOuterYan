SELECT *
FROM store_sales RIGHT OUTER JOIN (item LEFT OUTER JOIN date_dim ON ss_sold_date_sk = d_date_sk) ON ss_item_sk = i_item_sk
WHERE i_wholesale_cost > 100;
