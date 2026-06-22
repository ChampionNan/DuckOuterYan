SELECT *
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    FULL OUTER JOIN supplier ON n_nationkey = s_nationkey
    LEFT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
    RIGHT OUTER JOIN part ON ps_partkey = p_partkey
    FULL OUTER JOIN lineitem ON p_partkey = l_partkey
WHERE l_linenumber % 2 = 1;
