-- Customer-preserving report of fully shipped orders with lines shipped
-- before the April 1992 reporting cutoff. One comparison per filtered table.
-- Uses the TPC-H Q21 status predicate and a conventional shipping-date cutoff.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_shipdate < DATE '1992-04-01'
) ON c_custkey = o_custkey;
