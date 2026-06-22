SELECT *
FROM ((( region LEFT OUTER JOIN nation ON r_regionkey = n_regionkey) INNER JOIN customer ON n_nationkey = c_nationkey) RIGHT OUTER JOIN (( orders FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey) LEFT OUTER JOIN part ON l_partkey = p_partkey) ON c_custkey = o_custkey)
WHERE p_size >= 10;
