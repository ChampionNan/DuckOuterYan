SELECT *
FROM region RIGHT OUTER JOIN (nation INNER JOIN (customer FULL OUTER JOIN orders ON c_custkey = o_custkey) ON n_nationkey = c_nationkey) ON r_regionkey = n_regionkey
WHERE c_acctbal % 3 = 0;
