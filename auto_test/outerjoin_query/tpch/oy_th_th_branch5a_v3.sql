SELECT *
FROM (( customer LEFT OUTER JOIN orders ON c_custkey = o_custkey) INNER JOIN (( region RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey) FULL OUTER JOIN supplier ON n_nationkey = s_nationkey) ON c_nationkey = n_nationkey)
WHERE ps_availqty BETWEEN 1 AND 100;
