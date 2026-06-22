SELECT *
FROM (( customer RIGHT OUTER JOIN orders ON c_custkey = o_custkey) INNER JOIN (( part FULL OUTER JOIN supplier ON 1=1) LEFT OUTER JOIN lineitem ON p_partkey = l_partkey AND s_suppkey = l_suppkey) ON o_orderkey = l_orderkey)
WHERE o_orderkey < 50000;
