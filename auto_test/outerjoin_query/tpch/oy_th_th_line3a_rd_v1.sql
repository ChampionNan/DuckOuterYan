SELECT *
FROM region FULL OUTER JOIN (nation FULL OUTER JOIN supplier ON n_nationkey = s_nationkey) ON r_regionkey = n_regionkey
WHERE s_suppkey IN (2, 4, 6, 8, 10, 12, 14);
