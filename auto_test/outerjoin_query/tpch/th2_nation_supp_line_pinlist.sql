SELECT * FROM nation LEFT OUTER JOIN supplier ON n_nationkey=s_nationkey LEFT OUTER JOIN lineitem ON s_suppkey=l_suppkey WHERE n_nationkey IN (1, 2, 3, 5, 8, 13);
