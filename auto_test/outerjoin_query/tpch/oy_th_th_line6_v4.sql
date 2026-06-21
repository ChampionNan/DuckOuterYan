SELECT *
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    INNER JOIN supplier ON n_nationkey = s_nationkey
    FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey
    LEFT OUTER JOIN part ON ps_partkey = p_partkey
    RIGHT OUTER JOIN lineitem ON p_partkey = l_partkey
WHERE l_extendedprice <= 1000;
