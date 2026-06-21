SELECT *
FROM customer RIGHT OUTER JOIN (orders RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey
WHERE p_size >= 100 AND p_size <= 9000;
