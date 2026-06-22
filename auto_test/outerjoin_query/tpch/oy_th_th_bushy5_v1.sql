SELECT *
FROM (( customer RIGHT OUTER JOIN orders ON c_custkey = o_custkey) FULL OUTER JOIN (( part LEFT OUTER JOIN supplier ON 1=1) RIGHT OUTER JOIN lineitem ON p_partkey = l_partkey AND s_suppkey = l_suppkey) ON o_orderkey = l_orderkey)
WHERE s_acctbal IN (2, 4, 6, 8, 10, 12, 14);
