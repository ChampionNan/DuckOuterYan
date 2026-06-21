SELECT *
FROM ((( region RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey) FULL OUTER JOIN customer ON n_nationkey = c_nationkey) LEFT OUTER JOIN (( orders RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey) FULL OUTER JOIN part ON l_partkey = p_partkey) ON c_custkey = o_custkey)
WHERE r_regionkey > 100;
