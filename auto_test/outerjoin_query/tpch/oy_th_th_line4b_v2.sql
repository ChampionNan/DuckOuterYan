SELECT *
FROM region
    FULL OUTER JOIN nation ON r_regionkey = n_regionkey
    LEFT OUTER JOIN customer ON n_nationkey = c_nationkey
    RIGHT OUTER JOIN orders ON c_custkey = o_custkey
WHERE n_nationkey BETWEEN 50 AND 5000;
