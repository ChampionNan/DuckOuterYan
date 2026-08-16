SELECT *
FROM lineitem
    LEFT OUTER JOIN orders ON l_orderkey = o_orderkey
    RIGHT OUTER JOIN part ON l_partkey = p_partkey
    FULL OUTER JOIN supplier ON l_suppkey = s_suppkey
WHERE l_quantity IN (1, 5, 10, 50, 100, 500);
