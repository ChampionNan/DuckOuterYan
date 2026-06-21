SELECT *
FROM (( orders LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey) INNER JOIN ( part RIGHT OUTER JOIN partsupp ON p_partkey = ps_partkey) ON l_partkey = p_partkey)
WHERE p_size BETWEEN 50 AND 5000;
