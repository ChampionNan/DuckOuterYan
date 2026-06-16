SELECT * FROM nation LEFT OUTER JOIN supplier ON n_nationkey=s_nationkey LEFT OUTER JOIN lineitem ON s_suppkey=l_suppkey WHERE n_nationkey BETWEEN 1 AND 1000;
