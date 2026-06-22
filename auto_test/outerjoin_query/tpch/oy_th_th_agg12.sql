SELECT p_size, COUNT(*) AS cnt_val
FROM part
    FULL OUTER JOIN lineitem ON p_partkey = l_partkey
    FULL OUTER JOIN orders ON l_orderkey = o_orderkey
WHERE l_linenumber > 0 AND l_linenumber < 10000
GROUP BY p_size;
