SELECT *
FROM ((( region FULL OUTER JOIN nation ON r_regionkey = n_regionkey) LEFT OUTER JOIN customer ON n_nationkey = c_nationkey) RIGHT OUTER JOIN (( orders FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey) LEFT OUTER JOIN part ON l_partkey = p_partkey) ON c_custkey = o_custkey)
WHERE s_suppkey >= 10;
