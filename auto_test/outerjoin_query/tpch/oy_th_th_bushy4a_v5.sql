SELECT *
FROM (( orders FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey) INNER JOIN ( part LEFT OUTER JOIN partsupp ON p_partkey = ps_partkey) ON l_partkey = p_partkey)
WHERE l_extendedprice <= 1000;
