SELECT * FROM nation FULL OUTER JOIN supplier ON n_nationkey=s_nationkey LEFT OUTER JOIN customer ON n_nationkey=c_nationkey WHERE n_nationkey > 1 AND n_nationkey % 2 = 0;
