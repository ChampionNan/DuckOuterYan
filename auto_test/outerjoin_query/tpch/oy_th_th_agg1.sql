SELECT o_orderpriority, SUM(l_extendedprice) AS total_val
FROM customer
    RIGHT OUTER JOIN orders ON c_custkey = o_custkey
    FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE o_orderkey < 50000
GROUP BY o_orderpriority;
