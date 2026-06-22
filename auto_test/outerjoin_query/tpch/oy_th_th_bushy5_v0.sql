SELECT *
FROM (( customer LEFT OUTER JOIN orders ON c_custkey = o_custkey) RIGHT OUTER JOIN (( part FULL OUTER JOIN supplier ON 1=1) LEFT OUTER JOIN lineitem ON p_partkey = l_partkey AND s_suppkey = l_suppkey) ON o_orderkey = l_orderkey)
WHERE l_linenumber > 0 AND l_linenumber < 10000;
