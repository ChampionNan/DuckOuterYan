SELECT r_name, MIN(c_acctbal) AS lo_val
FROM region
    FULL OUTER JOIN nation ON r_regionkey = n_regionkey
    LEFT OUTER JOIN customer ON n_nationkey = c_nationkey
WHERE c_custkey BETWEEN 50 AND 5000
GROUP BY r_name;
