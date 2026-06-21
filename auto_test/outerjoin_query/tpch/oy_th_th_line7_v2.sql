SELECT *
FROM region
    FULL OUTER JOIN nation ON r_regionkey = n_regionkey
    LEFT OUTER JOIN customer ON n_nationkey = c_nationkey
    RIGHT OUTER JOIN orders ON c_custkey = o_custkey
    FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey
    LEFT OUTER JOIN supplier ON l_suppkey = s_suppkey
    RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE l_discount BETWEEN 50 AND 5000;
