SELECT i_brand, COUNT(*) AS cnt_val
FROM catalog_sales
    FULL OUTER JOIN item ON cs_item_sk = i_item_sk
    FULL OUTER JOIN customer ON cs_bill_customer_sk = c_customer_sk
WHERE cs_quantity > 0 AND cs_quantity < 10000
GROUP BY i_brand;
