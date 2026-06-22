SELECT *
FROM (( orders RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey) INNER JOIN ( part FULL OUTER JOIN partsupp ON p_partkey = ps_partkey) ON l_partkey = p_partkey)
WHERE l_orderkey < 50000;
