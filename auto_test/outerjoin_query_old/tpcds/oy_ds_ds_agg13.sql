SELECT i_brand, SUM(cs_sales_price) AS total_val
FROM catalog_sales
    LEFT OUTER JOIN item ON cs_item_sk = i_item_sk
    RIGHT OUTER JOIN customer ON cs_bill_customer_sk = c_customer_sk
WHERE cs_quantity IN (2, 4, 6, 8, 10, 12, 14)
GROUP BY i_brand;
