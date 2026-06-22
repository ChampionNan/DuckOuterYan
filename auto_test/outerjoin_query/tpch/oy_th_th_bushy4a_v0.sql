SELECT *
FROM (( orders LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey) RIGHT OUTER JOIN ( part FULL OUTER JOIN partsupp ON p_partkey = ps_partkey) ON l_partkey = p_partkey)
WHERE p_size >= 100 AND p_size <= 9000;
