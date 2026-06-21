SELECT *
FROM (( customer FULL OUTER JOIN orders ON c_custkey = o_custkey) LEFT OUTER JOIN (( region RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey) FULL OUTER JOIN supplier ON n_nationkey = s_nationkey) ON c_nationkey = n_nationkey)
WHERE p_size % 7 <> 0;
