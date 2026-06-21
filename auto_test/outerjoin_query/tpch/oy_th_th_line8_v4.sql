SELECT *
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    INNER JOIN customer ON n_nationkey = c_nationkey
    FULL OUTER JOIN orders ON c_custkey = o_custkey
    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey
    RIGHT OUTER JOIN part ON l_partkey = p_partkey
    INNER JOIN supplier ON l_suppkey = s_suppkey
    FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE p_size >= 100 AND p_size <= 9000;
