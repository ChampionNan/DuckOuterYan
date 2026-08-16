SELECT p_size, MAX(o_totalprice) AS hi_val
FROM part
    FULL OUTER JOIN lineitem ON p_partkey = l_partkey
    RIGHT OUTER JOIN orders ON l_orderkey = o_orderkey
WHERE l_linenumber < 200
GROUP BY p_size;
