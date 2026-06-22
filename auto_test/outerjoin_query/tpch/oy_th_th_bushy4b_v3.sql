SELECT *
FROM (( region LEFT OUTER JOIN nation ON r_regionkey = n_regionkey) INNER JOIN ( supplier RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE ps_supplycost IN (1, 5, 10, 50, 100, 500);
