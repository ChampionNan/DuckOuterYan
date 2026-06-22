SELECT *
FROM (( customer RIGHT OUTER JOIN orders ON c_custkey = o_custkey) INNER JOIN (( region FULL OUTER JOIN nation ON r_regionkey = n_regionkey) LEFT OUTER JOIN supplier ON n_nationkey = s_nationkey) ON c_nationkey = n_nationkey)
WHERE o_totalprice IN (2, 4, 6, 8, 10, 12, 14);
