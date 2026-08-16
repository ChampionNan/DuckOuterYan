SELECT *
FROM ((( region FULL OUTER JOIN nation ON r_regionkey = n_regionkey) INNER JOIN customer ON n_nationkey = c_nationkey) LEFT OUTER JOIN (( orders INNER JOIN lineitem ON o_orderkey = l_orderkey) RIGHT OUTER JOIN part ON l_partkey = p_partkey) ON c_custkey = o_custkey)
WHERE l_orderkey % 3 = 0;
