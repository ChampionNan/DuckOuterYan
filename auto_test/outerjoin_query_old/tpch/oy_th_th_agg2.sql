SELECT o_orderpriority, MIN(l_extendedprice) AS lo_val
FROM customer
    FULL OUTER JOIN orders ON c_custkey = o_custkey
    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE o_orderkey <= 1000
GROUP BY o_orderpriority;
