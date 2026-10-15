SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1998-07-01'
       AND l_receiptdate - l_commitdate > 110
) ON c_custkey = o_custkey;
