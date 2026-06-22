SELECT o_orderpriority, COUNT(*) AS cnt
FROM customer
    RIGHT OUTER JOIN orders ON c_custkey = o_custkey
    RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE l_extendedprice > 100
GROUP BY o_orderpriority;
