-- Customer-preserving report of fully shipped orders with lines shipped
-- during Q1 1994. One status predicate and one BETWEEN date-range predicate.
-- Q21 supplies the status condition; Q6/Q14 use shipping reporting periods.
-- This is a derived example; the quarter is not an unchanged benchmark period.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_shipdate BETWEEN DATE '1994-01-01' AND DATE '1994-03-31'
) ON c_custkey = o_custkey;
