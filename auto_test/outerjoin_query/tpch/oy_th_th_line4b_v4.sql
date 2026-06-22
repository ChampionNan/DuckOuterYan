SELECT *
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    INNER JOIN customer ON n_nationkey = c_nationkey
    FULL OUTER JOIN orders ON c_custkey = o_custkey
WHERE o_totalprice > 0 AND o_totalprice < 10000;
