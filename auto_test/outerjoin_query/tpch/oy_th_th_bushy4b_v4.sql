SELECT *
FROM (( region RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey) INNER JOIN ( supplier FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE l_quantity > 500;
