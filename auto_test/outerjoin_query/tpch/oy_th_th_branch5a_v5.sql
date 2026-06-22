SELECT *
FROM (( customer FULL OUTER JOIN orders ON c_custkey = o_custkey) INNER JOIN (( region LEFT OUTER JOIN nation ON r_regionkey = n_regionkey) INNER JOIN supplier ON n_nationkey = s_nationkey) ON c_nationkey = n_nationkey)
WHERE n_nationkey % 2 = 1;
