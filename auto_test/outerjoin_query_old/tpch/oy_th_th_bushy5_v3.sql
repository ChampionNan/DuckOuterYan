SELECT *
FROM (( customer LEFT OUTER JOIN orders ON c_custkey = o_custkey) INNER JOIN (( part RIGHT OUTER JOIN supplier ON 1=1) FULL OUTER JOIN lineitem ON p_partkey = l_partkey AND s_suppkey = l_suppkey) ON o_orderkey = l_orderkey)
WHERE l_linenumber > 500;
