SELECT *
FROM region
    FULL OUTER JOIN nation ON r_regionkey = n_regionkey
    LEFT OUTER JOIN customer ON n_nationkey = c_nationkey
    RIGHT OUTER JOIN orders ON c_custkey = o_custkey
    FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey
    LEFT OUTER JOIN part ON l_partkey = p_partkey
    RIGHT OUTER JOIN supplier ON l_suppkey = s_suppkey
    FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE s_acctbal BETWEEN 1 AND 100;
