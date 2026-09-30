-- Orders placed before 1997 with late receipts; preserve unmatched customers.
-- The lineitem predicate is taken directly from TPC-H Q21.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate > l_commitdate
) ON c_custkey = o_custkey;
