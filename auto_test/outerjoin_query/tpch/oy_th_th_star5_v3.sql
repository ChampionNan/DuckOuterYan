SELECT *
FROM lineitem
    LEFT OUTER JOIN orders ON l_orderkey = o_orderkey
    INNER JOIN part ON l_partkey = p_partkey
    RIGHT OUTER JOIN supplier ON l_suppkey = s_suppkey
    FULL OUTER JOIN nation ON s_nationkey = n_nationkey
WHERE s_suppkey < 200;
