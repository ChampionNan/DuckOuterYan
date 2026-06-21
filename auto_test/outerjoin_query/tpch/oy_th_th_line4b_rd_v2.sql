SELECT *
FROM region FULL OUTER JOIN (nation INNER JOIN (customer LEFT OUTER JOIN orders ON c_custkey = o_custkey) ON n_nationkey = c_nationkey) ON r_regionkey = n_regionkey
WHERE l_linenumber > 0 AND l_linenumber < 10000;
