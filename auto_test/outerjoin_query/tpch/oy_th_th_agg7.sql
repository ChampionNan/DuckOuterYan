SELECT n_regionkey, SUM(s_acctbal) AS tot_bal, COUNT(*) AS n_supp
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    FULL OUTER JOIN supplier ON n_nationkey = s_nationkey
WHERE n_nationkey % 2 = 1
GROUP BY n_regionkey;
