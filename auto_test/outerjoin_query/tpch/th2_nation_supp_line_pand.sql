SELECT * FROM nation LEFT OUTER JOIN supplier ON n_nationkey=s_nationkey LEFT OUTER JOIN lineitem ON s_suppkey=l_suppkey WHERE n_nationkey > 1 AND n_nationkey % 2 = 0;
