SELECT * FROM (region RIGHT OUTER JOIN (nation RIGHT OUTER JOIN supplier ON n_nationkey=s_nationkey) ON r_regionkey=n_regionkey);
