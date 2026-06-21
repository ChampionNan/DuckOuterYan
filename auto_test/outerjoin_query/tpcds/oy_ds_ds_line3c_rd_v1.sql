SELECT *
FROM store_sales LEFT OUTER JOIN (item RIGHT OUTER JOIN date_dim ON ss_sold_date_sk = d_date_sk) ON ss_item_sk = i_item_sk
WHERE i_item_sk >= 100 AND i_item_sk <= 9000;
