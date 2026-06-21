SELECT *
FROM customer
    RIGHT OUTER JOIN orders ON c_custkey = o_custkey
    RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE o_orderkey > 500;
