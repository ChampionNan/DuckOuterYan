-- Line amounts for orders placed in 1995 and received after the committed date.
-- Preserve customers with no qualifying late-received order line.
-- Relative to the original paper SQL, replace only the lineitem AIR predicate.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate >= DATE '1995-01-01'
       AND o_orderdate < DATE '1996-01-01'
       AND l_receiptdate > l_commitdate
) ON c_custkey = o_custkey;
