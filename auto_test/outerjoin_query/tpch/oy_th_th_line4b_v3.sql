SELECT *
FROM region
    LEFT OUTER JOIN nation ON r_regionkey = n_regionkey
    INNER JOIN customer ON n_nationkey = c_nationkey
    RIGHT OUTER JOIN orders ON c_custkey = o_custkey
WHERE c_acctbal % 3 = 0;
