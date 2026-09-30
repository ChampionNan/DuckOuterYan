-- Completed-order line detail for high-balance BUILDING customers in calendar 1995.
-- Preserve customers with no qualifying completed order in this period.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND o_orderdate >= DATE '1995-01-01'
       AND o_orderdate < DATE '1996-01-01'
) ON c_custkey = o_custkey
WHERE c_mktsegment = 'BUILDING'
  AND c_acctbal >= 9000;
