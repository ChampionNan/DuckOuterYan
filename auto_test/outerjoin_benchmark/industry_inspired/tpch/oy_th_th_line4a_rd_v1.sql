SELECT *
FROM region FULL OUTER JOIN (nation FULL OUTER JOIN (supplier FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey) ON r_regionkey = n_regionkey
WHERE s_suppkey < 200;
