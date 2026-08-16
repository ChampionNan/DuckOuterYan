SELECT *
FROM region RIGHT OUTER JOIN (nation RIGHT OUTER JOIN supplier ON n_nationkey = s_nationkey) ON r_regionkey = n_regionkey
WHERE r_regionkey > 0 AND r_regionkey < 10000;
