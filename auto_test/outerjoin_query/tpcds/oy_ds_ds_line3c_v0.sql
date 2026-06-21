SELECT *
FROM store_sales
    LEFT OUTER JOIN item ON ss_item_sk = i_item_sk
    RIGHT OUTER JOIN date_dim ON ss_sold_date_sk = d_date_sk
WHERE s_number_employees IN (2, 4, 6, 8, 10, 12, 14);
