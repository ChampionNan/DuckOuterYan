-- Completed-order line detail for order lines with quantity at least 50.
-- Preserve all customers, including those with no qualifying order line.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_quantity >= 50
) ON c_custkey = o_custkey;
