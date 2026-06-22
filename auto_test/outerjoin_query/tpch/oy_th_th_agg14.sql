SELECT p_size, MIN(o_totalprice) AS lo_val
FROM part
    RIGHT OUTER JOIN lineitem ON p_partkey = l_partkey
    LEFT OUTER JOIN orders ON l_orderkey = o_orderkey
WHERE l_linenumber % 2 = 1
GROUP BY p_size;
