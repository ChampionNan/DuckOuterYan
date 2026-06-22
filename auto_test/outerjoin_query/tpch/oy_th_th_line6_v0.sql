SELECT *
FROM region
    LEFT OUTER JOIN nation ON r_regionkey = n_regionkey
    RIGHT OUTER JOIN supplier ON n_nationkey = s_nationkey
    FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey
    LEFT OUTER JOIN part ON ps_partkey = p_partkey
    RIGHT OUTER JOIN lineitem ON p_partkey = l_partkey
WHERE l_extendedprice IN (2, 4, 6, 8, 10, 12, 14);
