SELECT p_size, SUM(o_totalprice) AS total_val
FROM part
    LEFT OUTER JOIN lineitem ON p_partkey = l_partkey
    RIGHT OUTER JOIN orders ON l_orderkey = o_orderkey
WHERE l_linenumber IN (2, 4, 6, 8, 10, 12, 14)
GROUP BY p_size;
