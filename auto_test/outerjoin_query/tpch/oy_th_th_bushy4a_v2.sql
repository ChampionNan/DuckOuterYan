SELECT *
FROM (( orders FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey) LEFT OUTER JOIN ( part RIGHT OUTER JOIN partsupp ON p_partkey = ps_partkey) ON l_partkey = p_partkey)
WHERE c_acctbal >= 10;
