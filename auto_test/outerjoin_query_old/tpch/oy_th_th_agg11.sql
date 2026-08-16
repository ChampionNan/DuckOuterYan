SELECT r_name, MAX(c_acctbal) AS hi_val
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    RIGHT OUTER JOIN customer ON n_nationkey = c_nationkey
WHERE c_custkey % 3 = 0
GROUP BY r_name;
