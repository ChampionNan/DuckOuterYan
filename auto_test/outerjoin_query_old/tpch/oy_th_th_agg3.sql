SELECT o_orderpriority, MAX(l_extendedprice) AS hi_val
FROM customer
    RIGHT OUTER JOIN orders ON c_custkey = o_custkey
    RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE o_orderkey IN (1, 5, 10, 50, 100, 500)
GROUP BY o_orderpriority;
