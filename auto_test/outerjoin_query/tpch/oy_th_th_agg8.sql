SELECT r_name, COUNT(*) AS cnt_val
FROM region
    LEFT OUTER JOIN nation ON r_regionkey = n_regionkey
    RIGHT OUTER JOIN customer ON n_nationkey = c_nationkey
WHERE c_custkey > 100
GROUP BY r_name;
