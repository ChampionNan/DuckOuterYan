SELECT *
FROM region LEFT OUTER JOIN (nation INNER JOIN (customer RIGHT OUTER JOIN orders ON c_custkey = o_custkey) ON n_nationkey = c_nationkey) ON r_regionkey = n_regionkey
WHERE n_nationkey BETWEEN 50 AND 5000;
