SELECT *
FROM region FULL OUTER JOIN (nation INNER JOIN (customer LEFT OUTER JOIN (orders INNER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey) ON n_nationkey = c_nationkey) ON r_regionkey = n_regionkey
WHERE s_suppkey > 500;
