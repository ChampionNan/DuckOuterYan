-- Review late-received lines of completed orders with quantity >= 25 and discount >= 5%.
-- Preserve all customers, including those with no qualifying order line.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_receiptdate > l_commitdate
       AND l_quantity >= 25
       AND l_discount >= 0.05
) ON c_custkey = o_custkey;
