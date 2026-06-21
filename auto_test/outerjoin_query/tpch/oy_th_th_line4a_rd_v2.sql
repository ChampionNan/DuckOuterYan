SELECT *
FROM region FULL OUTER JOIN (nation INNER JOIN (supplier LEFT OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey) ON r_regionkey = n_regionkey
WHERE l_quantity IN (1, 5, 10, 50, 100, 500);
