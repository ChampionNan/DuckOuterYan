SELECT *
FROM (( lineitem RIGHT OUTER JOIN part ON l_partkey = p_partkey) FULL OUTER JOIN (( nation LEFT OUTER JOIN region ON n_regionkey = r_regionkey) RIGHT OUTER JOIN supplier ON n_nationkey = s_nationkey) ON l_suppkey = s_suppkey)
WHERE p_partkey IN (2, 4, 6, 8, 10, 12, 14);
