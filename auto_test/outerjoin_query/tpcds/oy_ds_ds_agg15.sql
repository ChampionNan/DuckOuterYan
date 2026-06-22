SELECT i_brand, MAX(cs_sales_price) AS hi_val
FROM catalog_sales
    FULL OUTER JOIN item ON cs_item_sk = i_item_sk
    RIGHT OUTER JOIN customer ON cs_bill_customer_sk = c_customer_sk
WHERE cs_quantity < 200
GROUP BY i_brand;
