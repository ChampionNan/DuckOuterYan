SELECT *
FROM lineitem
    LEFT OUTER JOIN orders ON l_orderkey = o_orderkey
    RIGHT OUTER JOIN part ON l_partkey = p_partkey
    FULL OUTER JOIN supplier ON l_suppkey = s_suppkey
    LEFT OUTER JOIN nation ON s_nationkey = n_nationkey
WHERE p_partkey > 0 AND p_partkey < 10000;
