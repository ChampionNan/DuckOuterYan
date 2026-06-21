SELECT *
FROM customer
    FULL OUTER JOIN orders ON c_custkey = o_custkey
    FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE l_orderkey >= 100 AND l_orderkey <= 9000;
