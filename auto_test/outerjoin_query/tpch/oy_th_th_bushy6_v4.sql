SELECT *
FROM ((( region RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey) INNER JOIN customer ON n_nationkey = c_nationkey) FULL OUTER JOIN (( orders LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey) RIGHT OUTER JOIN part ON l_partkey = p_partkey) ON c_custkey = o_custkey)
WHERE p_partkey % 3 = 0;
