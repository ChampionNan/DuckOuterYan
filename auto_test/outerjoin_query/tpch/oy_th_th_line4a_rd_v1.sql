SELECT *
FROM region RIGHT OUTER JOIN (nation INNER JOIN (supplier FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey) ON r_regionkey = n_regionkey
WHERE o_totalprice <= 1000;
