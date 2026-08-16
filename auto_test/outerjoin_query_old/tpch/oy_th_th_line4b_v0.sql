SELECT *
FROM region
    LEFT OUTER JOIN nation ON r_regionkey = n_regionkey
    RIGHT OUTER JOIN customer ON n_nationkey = c_nationkey
    FULL OUTER JOIN orders ON c_custkey = o_custkey
WHERE c_acctbal <= 1000;
