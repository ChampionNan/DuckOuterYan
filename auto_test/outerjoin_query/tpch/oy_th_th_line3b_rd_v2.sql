SELECT *
FROM customer LEFT OUTER JOIN (orders RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey
WHERE o_orderkey >= 10;
