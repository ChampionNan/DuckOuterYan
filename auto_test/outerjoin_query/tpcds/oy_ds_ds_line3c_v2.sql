SELECT *
FROM store_sales
    FULL OUTER JOIN item ON ss_item_sk = i_item_sk
    LEFT OUTER JOIN date_dim ON ss_sold_date_sk = d_date_sk
WHERE ss_net_profit < 200;
