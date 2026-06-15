SELECT * FROM (region LEFT OUTER JOIN (nation LEFT OUTER JOIN supplier ON n_nationkey=s_nationkey) ON r_regionkey=n_regionkey);
