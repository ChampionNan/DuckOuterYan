SELECT *
FROM lineitem
    RIGHT OUTER JOIN orders ON l_orderkey = o_orderkey
    INNER JOIN part ON l_partkey = p_partkey
    FULL OUTER JOIN supplier ON l_suppkey = s_suppkey
    LEFT OUTER JOIN nation ON s_nationkey = n_nationkey
WHERE c_custkey < 50000;
