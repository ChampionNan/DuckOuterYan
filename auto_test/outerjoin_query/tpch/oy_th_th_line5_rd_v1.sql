SELECT *
FROM region RIGHT OUTER JOIN (nation INNER JOIN (customer FULL OUTER JOIN (orders LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey) ON n_nationkey = c_nationkey) ON r_regionkey = n_regionkey
WHERE l_linenumber BETWEEN 1 AND 100;
