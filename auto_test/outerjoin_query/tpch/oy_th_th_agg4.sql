SELECT r_name, COUNT(*) AS cnt, MAX(c_acctbal) AS max_bal
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    LEFT OUTER JOIN customer ON n_nationkey = c_nationkey
WHERE c_acctbal % 3 = 0
GROUP BY r_name;
