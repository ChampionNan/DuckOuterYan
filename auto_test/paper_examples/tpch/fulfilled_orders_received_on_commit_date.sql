-- Completed-order lines received exactly on the committed delivery date.
-- Preserve all customers, including those with no qualifying order line.
-- TPC-H Q21 uses the late-receipt comparison; this example checks equality instead.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_receiptdate = l_commitdate
) ON c_custkey = o_custkey;
