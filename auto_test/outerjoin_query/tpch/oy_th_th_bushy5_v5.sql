SELECT *
FROM (( customer FULL OUTER JOIN orders ON c_custkey = o_custkey) INNER JOIN (( part LEFT OUTER JOIN supplier ON 1=1) INNER JOIN lineitem ON p_partkey = l_partkey AND s_suppkey = l_suppkey) ON o_orderkey = l_orderkey)
WHERE c_acctbal > 100;
