SELECT o_orderpriority, COUNT(*) AS cnt_val
FROM customer
    LEFT OUTER JOIN orders ON c_custkey = o_custkey
    RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE o_orderkey < 200
GROUP BY o_orderpriority;
