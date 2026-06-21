SELECT *
FROM region
    LEFT OUTER JOIN nation ON r_regionkey = n_regionkey
    RIGHT OUTER JOIN customer ON n_nationkey = c_nationkey
    FULL OUTER JOIN orders ON c_custkey = o_custkey
    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey
    RIGHT OUTER JOIN supplier ON l_suppkey = s_suppkey
    FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE o_totalprice > 100;
