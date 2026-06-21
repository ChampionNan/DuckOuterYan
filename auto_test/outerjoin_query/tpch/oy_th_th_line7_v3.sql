SELECT *
FROM region
    LEFT OUTER JOIN nation ON r_regionkey = n_regionkey
    INNER JOIN customer ON n_nationkey = c_nationkey
    RIGHT OUTER JOIN orders ON c_custkey = o_custkey
    FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey
    LEFT OUTER JOIN supplier ON l_suppkey = s_suppkey
    INNER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE r_regionkey % 3 = 0;
