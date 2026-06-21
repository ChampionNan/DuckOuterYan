SELECT COUNT(*) AS cnt, SUM(cs_quantity) AS total_qty
FROM catalog_sales
    RIGHT OUTER JOIN item ON cs_item_sk = i_item_sk
    LEFT OUTER JOIN customer ON cs_bill_customer_sk = c_customer_sk
WHERE c_customer_sk < 200;
