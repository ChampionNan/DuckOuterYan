SELECT *
FROM (( region LEFT OUTER JOIN nation ON r_regionkey = n_regionkey) RIGHT OUTER JOIN ( supplier FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE p_partkey <= 1000;
