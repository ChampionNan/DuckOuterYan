SELECT *
FROM region LEFT OUTER JOIN (nation RIGHT OUTER JOIN supplier ON n_nationkey = s_nationkey) ON r_regionkey = n_regionkey
WHERE p_retailprice < 200;
