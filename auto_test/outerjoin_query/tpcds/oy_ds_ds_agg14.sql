SELECT i_brand, MIN(cs_sales_price) AS lo_val
FROM catalog_sales
    RIGHT OUTER JOIN item ON cs_item_sk = i_item_sk
    LEFT OUTER JOIN customer ON cs_bill_customer_sk = c_customer_sk
WHERE cs_quantity % 2 = 1
GROUP BY i_brand;
