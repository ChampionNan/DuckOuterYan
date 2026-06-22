SELECT *
FROM region
    FULL OUTER JOIN nation ON r_regionkey = n_regionkey
    LEFT OUTER JOIN customer ON n_nationkey = c_nationkey
    RIGHT OUTER JOIN orders ON c_custkey = o_custkey
    FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE c_custkey BETWEEN 1 AND 100;
