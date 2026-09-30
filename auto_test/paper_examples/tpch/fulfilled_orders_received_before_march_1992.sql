-- Fully shipped orders with lines received before the March 1992 report cutoff.
-- One ordinary comparison per filtered table; preserve unmatched customers.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_receiptdate < DATE '1992-03-01'
) ON c_custkey = o_custkey;
