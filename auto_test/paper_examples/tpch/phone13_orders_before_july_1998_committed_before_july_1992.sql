SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1998-07-01'
       AND l_commitdate < DATE '1992-07-01'
) ON c_custkey = o_custkey
WHERE c_phone LIKE '13%';
