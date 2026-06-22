SELECT *
FROM customer FULL OUTER JOIN (orders FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey
WHERE c_custkey > 100;
