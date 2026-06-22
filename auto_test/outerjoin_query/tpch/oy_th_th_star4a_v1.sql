SELECT *
FROM lineitem
    RIGHT OUTER JOIN orders ON l_orderkey = o_orderkey
    FULL OUTER JOIN part ON l_partkey = p_partkey
    LEFT OUTER JOIN supplier ON l_suppkey = s_suppkey
WHERE s_suppkey > 100;
