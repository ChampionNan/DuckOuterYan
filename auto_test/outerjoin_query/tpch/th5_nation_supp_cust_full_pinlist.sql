SELECT * FROM nation FULL OUTER JOIN supplier ON n_nationkey=s_nationkey LEFT OUTER JOIN customer ON n_nationkey=c_nationkey WHERE n_nationkey IN (1, 2, 3, 5, 8, 13);
