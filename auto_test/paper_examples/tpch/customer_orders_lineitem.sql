SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate >= DATE '1995-01-01'
       AND o_orderdate < DATE '1996-01-01'
       AND l_shipmode = 'AIR'
) ON c_custkey = o_custkey;
