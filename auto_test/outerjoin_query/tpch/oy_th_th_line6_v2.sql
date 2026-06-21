SELECT *
FROM region
    FULL OUTER JOIN nation ON r_regionkey = n_regionkey
    LEFT OUTER JOIN supplier ON n_nationkey = s_nationkey
    RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
    FULL OUTER JOIN part ON ps_partkey = p_partkey
    LEFT OUTER JOIN lineitem ON p_partkey = l_partkey
WHERE o_orderkey < 200;
