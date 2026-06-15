SELECT * FROM (region INNER JOIN (nation INNER JOIN supplier ON n_nationkey=s_nationkey) ON r_regionkey=n_regionkey);
