SELECT *
FROM (( customer RIGHT OUTER JOIN orders ON c_custkey = o_custkey) FULL OUTER JOIN (( region LEFT OUTER JOIN nation ON r_regionkey = n_regionkey) RIGHT OUTER JOIN supplier ON n_nationkey = s_nationkey) ON c_nationkey = n_nationkey)
WHERE o_totalprice IN (1, 5, 10, 50, 100, 500);
