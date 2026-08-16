SELECT *
FROM customer FULL OUTER JOIN (orders FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey
WHERE o_totalprice % 2 = 1;
