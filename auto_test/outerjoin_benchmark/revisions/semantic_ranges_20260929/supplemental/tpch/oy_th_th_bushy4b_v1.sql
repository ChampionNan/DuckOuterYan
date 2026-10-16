SELECT *
FROM (( region RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey) FULL OUTER JOIN ( supplier LEFT OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE n_nationkey < 50000;
