SELECT *
FROM lineitem
    RIGHT OUTER JOIN orders ON l_orderkey = o_orderkey
    INNER JOIN part ON l_partkey = p_partkey
    FULL OUTER JOIN supplier ON l_suppkey = s_suppkey
WHERE o_totalprice % 3 = 0;
