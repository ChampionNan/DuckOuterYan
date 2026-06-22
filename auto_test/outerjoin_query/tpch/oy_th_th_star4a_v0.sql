SELECT *
FROM lineitem
    LEFT OUTER JOIN orders ON l_orderkey = o_orderkey
    RIGHT OUTER JOIN part ON l_partkey = p_partkey
    FULL OUTER JOIN supplier ON l_suppkey = s_suppkey
WHERE l_discount >= 100 AND l_discount <= 9000;
