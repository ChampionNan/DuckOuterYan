SELECT * FROM ((region FULL OUTER JOIN nation ON r_regionkey=n_regionkey) RIGHT OUTER JOIN supplier ON n_nationkey=s_nationkey);
