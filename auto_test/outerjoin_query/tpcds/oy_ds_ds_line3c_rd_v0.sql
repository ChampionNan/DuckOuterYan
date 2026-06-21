SELECT *
FROM store_sales FULL OUTER JOIN (item FULL OUTER JOIN date_dim ON ss_sold_date_sk = d_date_sk) ON ss_item_sk = i_item_sk
WHERE cd_purchase_estimate > 500;
