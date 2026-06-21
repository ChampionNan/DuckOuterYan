SELECT *
FROM region LEFT OUTER JOIN (nation INNER JOIN (supplier RIGHT OUTER JOIN (partsupp FULL OUTER JOIN (part LEFT OUTER JOIN lineitem ON p_partkey = l_partkey) ON ps_partkey = p_partkey) ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey) ON r_regionkey = n_regionkey
WHERE n_nationkey IN (2, 4, 6, 8, 10, 12, 14);
