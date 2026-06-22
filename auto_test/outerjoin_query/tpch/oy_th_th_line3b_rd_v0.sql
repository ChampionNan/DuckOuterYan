SELECT *
FROM customer RIGHT OUTER JOIN (orders RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey
WHERE l_discount >= 100 AND l_discount <= 9000;
