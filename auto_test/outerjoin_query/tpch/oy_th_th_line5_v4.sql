SELECT *
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    INNER JOIN customer ON n_nationkey = c_nationkey
    FULL OUTER JOIN orders ON c_custkey = o_custkey
    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE l_orderkey >= 100 AND l_orderkey <= 9000;
