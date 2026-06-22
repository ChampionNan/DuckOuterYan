SELECT *
FROM lineitem
    FULL OUTER JOIN orders ON l_orderkey = o_orderkey
    LEFT OUTER JOIN part ON l_partkey = p_partkey
    RIGHT OUTER JOIN supplier ON l_suppkey = s_suppkey
WHERE p_partkey >= 10;
