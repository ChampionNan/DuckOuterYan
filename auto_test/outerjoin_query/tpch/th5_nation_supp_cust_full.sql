SELECT * FROM nation FULL OUTER JOIN supplier ON n_nationkey=s_nationkey LEFT OUTER JOIN customer ON n_nationkey=c_nationkey;
