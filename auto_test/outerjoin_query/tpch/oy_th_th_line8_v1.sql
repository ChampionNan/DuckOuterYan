SELECT *
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    FULL OUTER JOIN customer ON n_nationkey = c_nationkey
    LEFT OUTER JOIN orders ON c_custkey = o_custkey
    RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey
    FULL OUTER JOIN part ON l_partkey = p_partkey
    LEFT OUTER JOIN supplier ON l_suppkey = s_suppkey
    RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE n_nationkey % 7 <> 0;
