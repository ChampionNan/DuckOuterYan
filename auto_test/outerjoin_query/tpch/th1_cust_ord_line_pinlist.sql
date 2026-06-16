SELECT * FROM customer LEFT OUTER JOIN orders ON c_custkey=o_custkey LEFT OUTER JOIN lineitem ON o_orderkey=l_orderkey WHERE c_custkey IN (1, 2, 3, 5, 8, 13);
