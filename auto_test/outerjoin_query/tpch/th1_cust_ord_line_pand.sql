SELECT * FROM customer LEFT OUTER JOIN orders ON c_custkey=o_custkey LEFT OUTER JOIN lineitem ON o_orderkey=l_orderkey WHERE c_custkey > 1 AND c_custkey % 2 = 0;
