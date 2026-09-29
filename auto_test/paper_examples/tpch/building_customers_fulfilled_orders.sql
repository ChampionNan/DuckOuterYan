-- Completed-order line detail for high-balance customers in the BUILDING segment.
-- Preserve customers with no qualifying completed order.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
) ON c_custkey = o_custkey
WHERE c_mktsegment = 'BUILDING'
  AND c_acctbal >= 9000;
