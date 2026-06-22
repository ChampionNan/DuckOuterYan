SELECT r_name, SUM(c_acctbal) AS total_val
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    FULL OUTER JOIN customer ON n_nationkey = c_nationkey
WHERE c_custkey >= 10
GROUP BY r_name;
