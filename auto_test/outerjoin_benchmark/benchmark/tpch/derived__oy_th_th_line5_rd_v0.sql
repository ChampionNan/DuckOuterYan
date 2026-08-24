SELECT *
FROM region FULL OUTER JOIN (nation FULL OUTER JOIN (customer FULL OUTER JOIN (orders FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey) ON n_nationkey = c_nationkey) ON r_regionkey = n_regionkey
WHERE o_totalprice < 50000;
