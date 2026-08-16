SELECT *
FROM region
    LEFT OUTER JOIN nation ON r_regionkey = n_regionkey
    RIGHT OUTER JOIN supplier ON n_nationkey = s_nationkey
    FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey
    LEFT OUTER JOIN part ON ps_partkey = p_partkey
    RIGHT OUTER JOIN lineitem ON p_partkey = l_partkey
WHERE p_size IN (1, 5, 10, 50, 100, 500);
