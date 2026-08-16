SELECT *
FROM customer RIGHT OUTER JOIN (orders RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey
WHERE c_acctbal IN (2, 4, 6, 8, 10, 12, 14);
