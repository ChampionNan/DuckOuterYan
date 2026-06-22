SELECT *
FROM region LEFT OUTER JOIN (nation INNER JOIN (customer RIGHT OUTER JOIN (orders FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey) ON n_nationkey = c_nationkey) ON r_regionkey = n_regionkey
WHERE l_extendedprice % 7 <> 0;
