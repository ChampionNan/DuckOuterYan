SELECT *
FROM ((( region LEFT OUTER JOIN nation ON r_regionkey = n_regionkey) RIGHT OUTER JOIN customer ON n_nationkey = c_nationkey) FULL OUTER JOIN (( orders LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey) RIGHT OUTER JOIN part ON l_partkey = p_partkey) ON c_custkey = o_custkey)
WHERE p_partkey >= 100 AND p_partkey <= 9000;
