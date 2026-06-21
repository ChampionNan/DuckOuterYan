SELECT *
FROM lineitem
    FULL OUTER JOIN orders ON l_orderkey = o_orderkey
    LEFT OUTER JOIN part ON l_partkey = p_partkey
    RIGHT OUTER JOIN supplier ON l_suppkey = s_suppkey
    FULL OUTER JOIN nation ON s_nationkey = n_nationkey
WHERE r_regionkey % 2 = 1;
