-- Customer-preserving report of late deliveries on fully shipped orders,
-- restricted to the 5%-7% discount band used by TPC-H Q6.
-- Order status and late receipt predicates are taken from TPC-H Q21.
-- This is a derived outer-join example, not the complete Q6 or Q21 query.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_receiptdate > l_commitdate
       AND l_discount BETWEEN 0.05 AND 0.07
) ON c_custkey = o_custkey;
