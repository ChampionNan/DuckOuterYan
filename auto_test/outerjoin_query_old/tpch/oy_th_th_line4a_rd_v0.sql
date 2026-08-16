SELECT *
FROM region LEFT OUTER JOIN (nation INNER JOIN (supplier RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey) ON r_regionkey = n_regionkey
WHERE r_regionkey % 2 = 1;
