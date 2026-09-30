-- Orders placed before 1997 with early receipts; preserve unmatched customers.
-- Reverses the TPC-H Q21 late-receipt comparison for the early-delivery case.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate < l_commitdate
) ON c_custkey = o_custkey;
